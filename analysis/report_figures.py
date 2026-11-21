"""Figures and metrics of the integrated trials (17-Nov-2026) for the report, in English.

Usage:  python report_figures.py [output_dir]      (default: analysis/figures)
Input:  data/integration_2026-11-17/clean/
Output: fig_floor_base.png, fig_floor_heading.png, fig_floor_ball.png,
        fig_ramp_base.png, fig_ramp_ball.png, metrics_ball.csv, metrics_base.csv

Processing rules
  * Plate logs: ball position = columns 'inclinacion_x' (x) and 'inclinacion_y' (y), in mm (shifted LabVIEW header).
    Metrics start at the first sample with |x|,|y| < 40 mm plus 300 samples (ball placement).
  * Plate and base logs do not share a clock, so plate metrics are computed over the whole run.
  * Base arrival error = odometric error at the first sample inside the tolerance (the controller declares arrival);
    settled error = error at the end of the log.
  * Ramp slope = accelerometer estimate 'phi_cal' minus the 4.2 deg offset measured on level floor.
  * Speed error on the ramp = mean absolute error of the average wheel speed while |slope| > 7 deg.
  * Physical heading error (protractor, Lab 6) is entered by hand in PHYSICAL_HEADING.
"""
import glob
import os
import sys

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data", "integration_2026-11-17", "clean")
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "figures")
os.makedirs(OUT, exist_ok=True)
SKIP, OFFSET = 300, 4.2
# final heading measured with a protractor (deg); trials 6-7 only have an upper bound of 5 deg
PHYSICAL_HEADING = {1: 4.0, 2: 10.5, 3: 5.0, 4: 15.0, 5: 10.0, 6: 5.0, 7: 5.0}
UPPER_BOUND = {6, 7}

BLUE, CYAN, INK, MUTED, GREEN, RED, ORANGE = "#0070C0", "#00B0F0", "#1A1A1A", "#595959", "#1E7B34", "#C0392B", "#D9822B"
plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 12, "axes.titlesize": 13, "axes.titleweight": "bold",
    "axes.labelsize": 12, "xtick.labelsize": 11, "ytick.labelsize": 11, "legend.fontsize": 11,
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": "#E3E3E3",
    "axes.edgecolor": MUTED, "legend.frameon": False, "savefig.dpi": 300,
})


def take(f):
    return int(os.path.basename(f).split("toma")[1].split(".")[0])


# ----------------------------------------------------------------------------- loaders
def plate(kind):
    runs = []
    for f in sorted(glob.glob(os.path.join(DATA, f"control_balanceo_{kind}_17_11_toma*.csv")), key=take):
        d = pd.read_csv(f)
        x, y = d["inclinacion_x"].to_numpy(), d["inclinacion_y"].to_numpy()
        i0 = int(np.argmax((np.abs(x) < 40) & (np.abs(y) < 40))) + SKIP
        runs.append((take(f), x[i0:], y[i0:]))
    return runs


def base(kind):
    ini = pd.read_csv(os.path.join(DATA, "inicio_consigna_movil.csv")).set_index("archivo")
    runs = []
    for f in sorted(glob.glob(os.path.join(DATA, f"control_movil_{kind}_17_11_toma*.csv")), key=take):
        d = pd.read_csv(f)
        d["tt"] = d.t - ini.loc[os.path.basename(f), "primera_consigna_movil_t_original"]
        runs.append((take(f), d))
    return runs


# ----------------------------------------------------------------------------- metrics
def ball_metrics(scenario, runs):
    return [dict(scenario=scenario, trial=k, samples=len(x),
                 rmse_mm=np.sqrt(np.mean(x ** 2 + y ** 2)),
                 peak_mm=max(np.abs(x).max(), np.abs(y).max()),
                 in_band_pct=np.mean((np.abs(x) <= 20) & (np.abs(y) <= 20)) * 100,
                 bias_x_mm=x.mean(), bias_y_mm=y.mean()) for k, x, y in runs]


def base_metrics(floor, ramp):
    rows = []
    for k, d in floor:
        p = d.paso.to_numpy()
        ch = np.where(np.diff(p) != 0)[0]
        i1, i2 = ch[0], ch[1]
        il = int(np.argmax(d.llego.to_numpy() > 0))
        rows.append(dict(scenario="floor", trial=k,
                         arrival_err_seg1_cm=100 - d.x_odo[i1 + 1], arrival_err_seg2_cm=200 - d.x_odo[il],
                         arrival_heading_err_deg=360 - d.th_deg_odo[i2 + 1],
                         settled_err_cm=200 - d.x_odo.iloc[-1], settled_heading_err_deg=360 - d.th_deg_odo.iloc[-1],
                         max_lateral_cm=d.y_odo.abs().max(), physical_heading_err_deg=PHYSICAL_HEADING[k]))
    for k, d in ramp:
        il = int(np.argmax(d.llego.to_numpy() > 0))
        m = d.SpVel_M1 > 5
        phi = d.phi_cal - OFFSET
        e = (d.Vel_M1 + d.Vel_M2) / 2 - (d.SpVel_M1 + d.SpVel_M2) / 2
        rows.append(dict(scenario="ramp", trial=k, arrival_err_seg2_cm=260 - d.x_odo[il],
                         settled_err_cm=260 - d.x_odo.iloc[-1], max_lateral_cm=d.y_odo.abs().max(),
                         speed_mae_up_cms=np.mean(np.abs(e[m & (phi > 7)])),
                         speed_mae_down_cms=np.mean(np.abs(e[m & (phi < -7)])),
                         slope_up_deg=phi[m & (phi > 7)].mean(), slope_down_deg=phi[m & (phi < -7)].mean()))
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------- figures
def ball_fig(runs, fname):
    fig, axs = plt.subplots(1, 2, figsize=(7.2, 3.4), sharey=True, constrained_layout=True)
    for ax, j, lab in ((axs[0], 1, "x axis"), (axs[1], 2, "y axis")):
        ax.axhspan(-20, 20, color=GREEN, alpha=0.12, lw=0)
        for s in (40, -40):
            ax.axhline(s, color=RED, ls="--", lw=1.3)
        bp = ax.boxplot([r[j] for r in runs], widths=0.6, whis=(1, 99), showfliers=False, patch_artist=True,
                        medianprops=dict(color=INK, lw=1.6))
        for b in bp["boxes"]:
            b.set(facecolor=CYAN, edgecolor=BLUE, alpha=0.85)
        ax.set_xticks(range(1, len(runs) + 1), [str(r[0]) for r in runs])
        ax.set_xlabel("Trial")
        ax.set_title(lab, loc="left")
        ax.set_ylim(-60, 60)
    axs[0].set_ylabel("Ball position error [mm]")
    fig.legend(handles=[Patch(color=GREEN, alpha=0.3, label="±20 mm precision band"),
                        Line2D([], [], color=RED, ls="--", lw=1.3, label="±40 mm containment limit"),
                        Patch(facecolor=CYAN, edgecolor=BLUE, label="Box: 25–75 %, whiskers: 1–99 %")],
               loc="lower center", ncol=3, bbox_to_anchor=(0.5, -0.13), fontsize=10)
    fig.savefig(os.path.join(OUT, fname), bbox_inches="tight")
    plt.close(fig)


def floor_base_fig(runs):
    fig, axs = plt.subplots(2, 1, figsize=(7.2, 4.4), sharex=True, constrained_layout=True)
    for k, d in runs:
        d = d[d.tt >= -0.5]
        axs[0].plot(d.tt, d.x_odo, color=BLUE, lw=1.3, alpha=0.7)
        axs[1].plot(d.tt, d.th_deg_odo, color=BLUE, lw=1.3, alpha=0.7)
    for r in (100, 200):
        axs[0].axhline(r, color=INK, ls="--", lw=1.1)
    axs[1].axhline(360, color=INK, ls="--", lw=1.1)
    axs[0].set_ylabel("Distance [cm]")
    axs[1].set_ylabel("Heading [deg]")
    axs[1].set_xlabel("Time from the first speed set-point [s]")
    axs[0].text(1, 112, "segment 1 (100 cm)")
    axs[0].text(28.5, 125, "segment 2")
    axs[1].text(13, 240, "360° in-place turn")
    axs[0].legend(handles=[Line2D([], [], color=BLUE, lw=2, label="Odometry, 7 trials"),
                           Line2D([], [], color=INK, ls="--", lw=1.1, label="Reference")], loc="lower right")
    fig.savefig(os.path.join(OUT, "fig_floor_base.png"), bbox_inches="tight")
    plt.close(fig)


def floor_heading_fig(bm):
    f = bm[bm.scenario == "floor"].sort_values("trial")
    k = f.trial.to_numpy()
    phys = f.physical_heading_err_deg.to_numpy()
    fig, ax = plt.subplots(figsize=(7.2, 3.1), constrained_layout=True)
    for kk, v in zip(k, phys):
        if kk in UPPER_BOUND:
            ax.bar(kk, v, color="white", edgecolor=BLUE, hatch="//", lw=1.3, width=0.6)
        else:
            ax.bar(kk, v, color=BLUE, width=0.6)
    ax.plot(k, f.arrival_heading_err_deg, "D", color=ORANGE, ms=8, mec=INK, label="Odometry at arrival")
    ax.axhline(1, color=RED, ls="--", lw=1.3)
    ax.set_xticks(k)
    ax.set_xlabel("Trial")
    ax.set_ylabel("Heading error [deg]")
    ax.legend(handles=[Patch(color=BLUE, label="Measured, tight omni wheels"),
                       Patch(facecolor="white", edgecolor=BLUE, hatch="//", label="Measured, loosened wheels (upper bound)"),
                       Line2D([], [], marker="D", ls="", color=ORANGE, mec=INK, ms=8, label="Odometry at arrival"),
                       Line2D([], [], color=RED, ls="--", lw=1.3, label="1° tolerance")],
              loc="upper left", ncol=2, fontsize=10)
    ax.set_ylim(0, 22)
    fig.savefig(os.path.join(OUT, "fig_floor_heading.png"), bbox_inches="tight")
    plt.close(fig)


def ramp_base_fig(runs):
    fig, axs = plt.subplots(2, 1, figsize=(7.2, 4.4), sharex=True, constrained_layout=True)
    for k, d in runs:
        d = d[d.tt >= 0]
        v = ((d.Vel_M1 + d.Vel_M2) / 2).rolling(25, center=True, min_periods=1).mean()
        axs[0].plot(d.x_odo, d.phi_cal - OFFSET, color=BLUE, lw=1.1, alpha=0.7)
        axs[1].plot(d.x_odo, v, color=BLUE, lw=1.3, alpha=0.7)
    for r in (10, -10):
        axs[0].axhline(r, color=INK, ls="--", lw=1.1)
    axs[1].axhline(10, color=INK, ls="--", lw=1.1)
    axs[1].axhspan(9, 11, color=GREEN, alpha=0.12, lw=0)
    for xx, yy, t in ((55, 5.5, "ascent"), (120, -4.5, "level"), (185, -6.5, "descent")):
        axs[0].text(xx, yy, t, ha="center")
    axs[0].set_ylim(-14, 14)
    axs[1].set_ylim(6, 13)
    axs[0].set_ylabel("Slope [deg]")
    axs[1].set_ylabel("Speed [cm/s]")
    axs[1].set_xlabel("Distance along the route [cm]")
    axs[1].text(250, 10.5, "set-point 10 cm/s, ±1 cm/s band", ha="right", fontsize=10)
    axs[0].legend(handles=[Line2D([], [], color=BLUE, lw=2, label="6 trials")], loc="upper right")
    fig.savefig(os.path.join(OUT, "fig_ramp_base.png"), bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    pf, pr = plate("rutina"), plate("rampa")
    bf, br = base("rutina"), base("rampa")
    mb = pd.DataFrame(ball_metrics("floor", pf) + ball_metrics("ramp", pr))
    bm = base_metrics(bf, br)
    mb.round(2).to_csv(os.path.join(OUT, "metrics_ball.csv"), index=False)
    bm.round(3).to_csv(os.path.join(OUT, "metrics_base.csv"), index=False)
    ball_fig(pf, "fig_floor_ball.png")
    ball_fig(pr, "fig_ramp_ball.png")
    floor_base_fig(bf)
    floor_heading_fig(bm)
    ramp_base_fig(br)
    print(mb.round(1).to_string(index=False))
    print(bm.round(3).to_string(index=False))
    print("figures in", OUT)
