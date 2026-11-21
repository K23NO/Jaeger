"""English block diagrams for the report (one slide each in diagrams_en.pptx).

  1 electronic architecture   2 program flowchart (myRIO)
  3 base cascade control       4 ball-position control

Usage: python build_diagrams_en.py   -> diagrams_en.pptx in this folder.
Export to PNG with export_png.ps1 (PowerPoint) and crop with crop_png.py.
"""
import os

from lxml import etree
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

HERE = os.path.dirname(os.path.abspath(__file__))
BLUE, CYAN, INK, MUTED = RGBColor(0x00, 0x70, 0xC0), RGBColor(0x00, 0xB0, 0xF0), RGBColor(0x1A, 0x1A, 0x1A), RGBColor(0x59, 0x59, 0x59)
ORANGE, WHITE, TINT, POWER = RGBColor(0xB3, 0x4D, 0x0A), RGBColor(0xFF, 0xFF, 0xFF), RGBColor(0xEA, 0xF6, 0xFD), RGBColor(0xC0, 0x39, 0x2B)
PINK, YELLOW, GREENT, GREY = RGBColor(0xF8, 0xD7, 0xDA), RGBColor(0xFF, 0xF2, 0xC2), RGBColor(0xE2, 0xF0, 0xD9), RGBColor(0xE4, 0xE9, 0xF2)
PEACH, PANEL = RGBColor(0xFD, 0xEB, 0xD9), RGBColor(0xEE, 0xF1, 0xF5)
FONT = "Arial"


def I(v):
    return int(round(Inches(v)))


prs = Presentation()
prs.slide_width, prs.slide_height = I(20), I(11.25)


def new_slide():
    return prs.slides.add_slide(prs.slide_layouts[6])


def runs(p, parts, size, color, bold):
    for t, ov in parts:
        r = p.add_run()
        r.text = t
        r.font.name = FONT
        r.font.size = Pt(ov.get("size", size))
        r.font.bold = ov.get("bold", bold)
        r.font.italic = ov.get("italic", False)
        r.font.color.rgb = ov.get("color", color)
        if ov.get("sub"):
            r._r.get_or_add_rPr().set("baseline", "-25000")
        if ov.get("sup"):
            r._r.get_or_add_rPr().set("baseline", "30000")


def as_parts(t):
    return t if isinstance(t, list) else [(t, {})]


def box(s, x, y, w, h, text="", sub=None, shape=MSO_SHAPE.ROUNDED_RECTANGLE, fill=WHITE, line=CYAN, color=INK,
        size=16, sub_size=13, bold=True, radius=0.12, align=PP_ALIGN.CENTER):
    sh = s.shapes.add_shape(shape, I(x), I(y), I(w), I(h))
    if shape == MSO_SHAPE.ROUNDED_RECTANGLE:
        sh.adjustments[0] = radius
    if fill is None:
        sh.fill.background()
    else:
        sh.fill.solid()
        sh.fill.fore_color.rgb = fill
    if line is None:
        sh.line.fill.background()
    else:
        sh.line.color.rgb = line
        sh.line.width = Pt(1.5)
    sh.shadow.inherit = False
    tf = sh.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = I(0.05)
    tf.margin_top = tf.margin_bottom = I(0.02)
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = align
    if text:
        runs(p, as_parts(text), size, color, bold)
    if sub:
        p2 = tf.add_paragraph()
        p2.alignment = align
        runs(p2, as_parts(sub), sub_size, color if fill in (BLUE, POWER) else MUTED, False)
    return sh


def txt(s, x, y, w, h, text, size=14, color=INK, bold=False, align=PP_ALIGN.LEFT, italic=False):
    tb = s.shapes.add_textbox(I(x), I(y), I(w), I(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    p = tf.paragraphs[0]
    p.alignment = align
    parts = [(t, {**ov, "italic": ov.get("italic", italic)}) for t, ov in as_parts(text)]
    runs(p, parts, size, color, bold)
    return tb


def line(s, x1, y1, x2, y2, head=False, color=BLUE, width=1.75, dash=False):
    c = s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, I(x1), I(y1), I(x2), I(y2))
    c.line.color.rgb = color
    c.line.width = Pt(width)
    ln = c.line._get_or_add_ln()
    if dash:
        etree.SubElement(ln, qn("a:prstDash")).set("val", "dash")
    if head:
        t = etree.SubElement(ln, qn("a:tailEnd"))
        t.set("type", "triangle")
        t.set("w", "med")
        t.set("len", "med")


def path(s, pts, color=BLUE, width=1.75, head=True):
    for k in range(len(pts) - 1):
        line(s, *pts[k], *pts[k + 1], head=head and k == len(pts) - 2, color=color, width=width)


def summer(s, cx, cy, r=0.28):
    box(s, cx - r, cy - r, 2 * r, 2 * r, "Σ", shape=MSO_SHAPE.OVAL, fill=WHITE, line=INK, size=15, bold=False)


# =========================================================================== 1 electronics
s = new_slide()
cA, cB, cC = 0.5, 5.3, 11.4
box(s, cA, 0.5, 3.8, 1.2, "Battery 12 V", "NiMH 3000 mAh · 20 A fuse", fill=POWER, line=None, color=WHITE, size=18, sub_size=14)
box(s, cA, 2.3, 3.8, 1.0, "ON/OFF switch", fill=WHITE, line=POWER, size=17, bold=False)
box(s, cA, 3.9, 3.8, 1.2, "XL4015 buck", "12 V → 6 V, 5 A", fill=WHITE, line=POWER, size=17, sub_size=14)
box(s, cA, 6.3, 3.8, 1.2, "Power bank", "5 V, ≥ 2.5 A", fill=WHITE, line=POWER, size=17, sub_size=14)
box(s, cB, 0.5, 4.8, 1.5, "NI myRIO-1900", "LabVIEW RT · onboard accelerometer", fill=BLUE, line=None, color=WHITE, size=20, sub_size=14)
box(s, cB, 3.5, 4.8, 1.5, "Board 1 (custom PCB)", "MXP A/B ↔ terminals · 6 V to servos", fill=TINT, line=BLUE, size=18, sub_size=14)
box(s, cB, 6.3, 4.8, 1.2, "Raspberry Pi 3 + Brio", "60 fps vision", fill=WHITE, line=CYAN, size=17, sub_size=14)
box(s, cC, 0.8, 3.9, 1.1, "Cytron MDD10A", "2 × 10 A driver · 12 V", size=17, sub_size=14)
box(s, cC, 2.6, 3.9, 1.1, "2 TorqueNADO motors", "with encoder", size=17, sub_size=14)
box(s, cC, 4.4, 3.9, 1.1, "2 HS-485HB servos", "plate x and y axes", size=17, sub_size=14)
line(s, cA + 1.9, 1.7, cA + 1.9, 2.3, head=True, color=POWER)
line(s, cA + 1.9, 3.3, cA + 1.9, 3.9, head=True, color=POWER)
line(s, cA + 3.8, 2.8, cB, 1.25, head=True, color=POWER)
txt(s, cA + 3.9, 1.3, 0.8, 0.4, "12 V", size=14, color=POWER)
line(s, cA + 3.8, 4.5, cB, 4.25, head=True, color=POWER)
line(s, cA + 3.8, 6.9, cB, 6.9, head=True, color=POWER)
line(s, cB + 2.4, 2.0, cB + 2.4, 3.5, color=BLUE)
txt(s, cB + 2.55, 2.55, 2.2, 0.4, "MXP jumpers", size=14, color=MUTED)
line(s, cB + 2.4, 6.3, cB + 2.4, 5.0, head=True, color=BLUE)
txt(s, cB + 2.55, 5.45, 2.2, 0.4, "UART 230 400", size=14, color=MUTED)
line(s, cB + 4.8, 3.8, cC, 1.35, head=True)
line(s, cC + 1.95, 1.9, cC + 1.95, 2.6, head=True)
line(s, cC, 3.15, cB + 4.8, 4.1, head=True)
line(s, cB + 4.8, 4.45, cC, 4.95, head=True)
txt(s, cB + 4.85, 1.75, 1.2, 0.4, "PWM, DIR", size=12, color=MUTED)
txt(s, cB + 5.25, 3.95, 1.3, 0.4, "encoders", size=12, color=MUTED)
txt(s, cB + 4.95, 5.0, 1.4, 0.4, "servo PWM", size=12, color=MUTED)
txt(s, cC, 6.3, 3.9, 0.4, [("━  ", {"bold": True, "color": POWER}), ("power", {})], size=15)
txt(s, cC, 6.8, 3.9, 0.4, [("━  ", {"bold": True, "color": BLUE}), ("signal / data", {})], size=15)

# =========================================================================== 2 flowchart
s = new_slide()
TERM, PREP, DATA = MSO_SHAPE.FLOWCHART_TERMINATOR, MSO_SHAPE.FLOWCHART_PREPARATION, MSO_SHAPE.PARALLELOGRAM
PROC, DEC, DOC = MSO_SHAPE.FLOWCHART_PROCESS, MSO_SHAPE.FLOWCHART_DECISION, MSO_SHAPE.FLOWCHART_DOCUMENT
STYLE = {TERM: dict(fill=BLUE, line=None, color=WHITE), PREP: dict(fill=TINT, line=BLUE, color=INK),
         DATA: dict(fill=WHITE, line=BLUE, color=INK), PROC: dict(fill=WHITE, line=CYAN, color=INK),
         DEC: dict(fill=WHITE, line=ORANGE, color=INK), DOC: dict(fill=WHITE, line=BLUE, color=INK)}


def node(kind, x, y, w, h, text, sub=None, size=14, sub_size=12):
    sh = box(s, x, y, w, h, text, sub=sub, shape=kind, size=size, sub_size=sub_size, **STYLE[kind])
    if kind == DATA:
        sh.adjustments[0] = 0.14
    return sh


def lab(x, y, t, color=ORANGE):
    txt(s, x, y, 0.6, 0.3, t, size=13, color=color, bold=True)


LBL_X, LBL_W, TRUNK, X0, XR, EXIT, PH, DH = 0.3, 1.9, 2.5, 2.78, 18.75, 19.15, 0.95, 1.25


def lane_xs(n, w):
    g = (XR - X0 - n * w) / (n - 1)
    return [X0 + i * (w + g) for i in range(n)], g


yi = 0.3
node(TERM, 0.3, yi + 0.1, 1.6, 0.7, "Start", size=16)
node(PREP, TRUNK - 0.25, yi, 7.3, 0.9, "Initialization", sub="UART 230 400 · motor and servo PWM · encoders · accelerometer", size=15, sub_size=13)
line(s, 1.9, yi + 0.45, TRUNK - 0.25, yi + 0.45, head=True)
legend = [(TERM, "Start / end"), (PREP, "Preparation"), (DATA, "Input / output"), (PROC, "Process"), (DEC, "Decision"), (DOC, "Log")]
for k, (kind, t) in enumerate(legend):
    x, y = 10.15 + (k % 3) * 3.1, yi + 0.05 + (k // 3) * 0.45
    box(s, x, y, 0.6, 0.32, "", shape=kind, **{**STYLE[kind], "color": INK})
    txt(s, x + 0.7, y + 0.02, 2.3, 0.32, t, size=13, color=MUTED)

ya = 1.6
box(s, LBL_X, ya, LBL_W, PH, "Plate loop", sub="at the camera rate", fill=BLUE, line=None, color=WHITE, size=15, sub_size=12)
wa = 2.2
xa, ga = lane_xs(6, wa)
mid_a = ya + PH / 2
node(DATA, xa[0], ya, wa, PH, "Read UART packet", "x, y, valid, sequence")
node(DEC, xa[1], mid_a - DH / 2, wa, DH, "Valid packet?")
node(PROC, xa[2], ya, wa, PH, "PID on x and y", "plate tilt")
node(PROC, xa[3], ya, wa, PH, "Tilt → servo angle", "arm geometry")
node(DATA, xa[4], ya, wa, PH, "Servo PWM", "x and y axes")
node(DEC, xa[5], mid_a - DH / 2, wa, DH, "STOP?")
for i in range(5):
    line(s, xa[i] + wa, mid_a, xa[i + 1], mid_a, head=True)
lab(xa[1] + wa + 0.03, mid_a - 0.35, "Yes")
yn = ya + PH + 0.25
node(PROC, xa[1] + 0.1, yn, wa - 0.2, 0.6, "Use last x, y", size=13)
line(s, xa[1] + wa / 2, mid_a + DH / 2, xa[1] + wa / 2, yn, head=True)
lab(xa[1] + wa / 2 + 0.3, mid_a + DH / 2 - 0.2, "No")
jx = xa[1] + wa + ga / 2
path(s, [(xa[1] + wa - 0.1, yn + 0.3), (jx, yn + 0.3), (jx, mid_a)])
yl = yn + 0.8
path(s, [(xa[5] + wa / 2, mid_a + DH / 2), (xa[5] + wa / 2, yl), (xa[0] + wa / 2, yl), (xa[0] + wa / 2, ya + PH)], color=CYAN)
lab(xa[5] + wa / 2 + 0.3, mid_a + DH / 2 - 0.2, "No", CYAN)
txt(s, xa[0] + wa / 2 + 0.12, yl + 0.02, 3.5, 0.3, "repeat every cycle", size=12, color=MUTED)
line(s, xa[5] + wa, mid_a, EXIT, mid_a, color=ORANGE)
lab(xa[5] + wa + 0.02, mid_a - 0.35, "Yes")

yb = 4.0
box(s, LBL_X, yb, LBL_W, PH, "Base loop", sub="every 10 ms", fill=BLUE, line=None, color=WHITE, size=15, sub_size=12)
wb = 1.95
xb, gb = lane_xs(7, wb)
mid_b = yb + PH / 2
node(DATA, xb[0], yb, wb, PH, "Read encoders", "and accelerometer", size=13)
node(PROC, xb[1], yb, wb, PH, "Slope and odometry", "x, y, θ", size=13)
node(PROC, xb[2], yb, wb, PH, "Inverse kinematics", "vR, vL", size=13)
node(PROC, xb[3], yb, wb, PH, "PI per wheel", "+ feedforward", size=13)
node(DEC, xb[4], mid_b - DH / 2, wb, DH, "Fault or stall?", size=13)
node(DATA, xb[5], yb, wb, PH, "PWM and DIR", "Cytron → motors", size=13)
node(DEC, xb[6], mid_b - DH / 2, wb, DH, "STOP?", size=13)
for i in range(6):
    line(s, xb[i] + wb, mid_b, xb[i + 1], mid_b, head=True)
lab(xb[4] + wb + 0.03, mid_b - 0.35, "No")
yf = yb + PH + 0.25
node(DATA, xb[4] + 0.05, yf, wb - 0.1, 0.6, "PWM = 0 on that wheel", size=12)
line(s, xb[4] + wb / 2, mid_b + DH / 2, xb[4] + wb / 2, yf, head=True)
lab(xb[4] + wb / 2 + 0.3, mid_b + DH / 2 - 0.2, "Yes")
jxb = xb[5] + wb + gb / 2
path(s, [(xb[4] + wb - 0.1, yf + 0.3), (jxb, yf + 0.3), (jxb, mid_b)])
ylb = yf + 0.8
path(s, [(xb[6] + wb / 2, mid_b + DH / 2), (xb[6] + wb / 2, ylb), (xb[0] + wb / 2, ylb), (xb[0] + wb / 2, yb + PH)], color=CYAN)
lab(xb[6] + wb / 2 + 0.3, mid_b + DH / 2 - 0.2, "No", CYAN)
txt(s, xb[0] + wb / 2 + 0.12, ylb + 0.02, 3.5, 0.3, "repeat every cycle", size=12, color=MUTED)
line(s, xb[6] + wb, mid_b, EXIT, mid_b, color=ORANGE)
lab(xb[6] + wb + 0.02, mid_b - 0.35, "Yes")
line(s, TRUNK, yi + 0.9, TRUNK, mid_b)
line(s, TRUNK, mid_a, xa[0] + 0.12, mid_a, head=True)
line(s, TRUNK, mid_b, xb[0] + 0.12, mid_b, head=True)

ys = 6.35
sw, sg = 2.6, 0.45
steps = [(DATA, "PWM = 0", "motors and servos"), (DOC, "Save CSV", "trial log"), (PROC, "Close UART", "VISA Close"), (PROC, "Reset myRIO", None)]
xs = [X0 + k * (sw + sg) for k in range(len(steps))]
for k, (kind, t, sub) in enumerate(steps):
    node(kind, xs[k], ys, sw, 0.85, t, sub, size=14)
    if k:
        line(s, xs[k - 1] + sw, ys + 0.425, xs[k], ys + 0.425, head=True)
fin = xs[-1] + sw + sg
node(TERM, fin, ys + 0.1, 1.5, 0.65, "End", size=16)
line(s, xs[-1] + sw, ys + 0.425, fin, ys + 0.425, head=True)
yu = ys + 1.05
path(s, [(EXIT, mid_a), (EXIT, yu), (xs[0] + sw / 2, yu), (xs[0] + sw / 2, ys + 0.85)], color=ORANGE)
txt(s, 0.3, ys + 0.15, 2.3, 0.3, "Shutdown", size=15, color=ORANGE, bold=True)
txt(s, 0.3, ys + 0.5, 2.3, 0.3, "STOP ALL pressed", size=12, color=MUTED)

# =========================================================================== 3 base cascade control
s = new_slide()
y0 = 2.2
box(s, 4.6, 0.9, 8.4, 3.0, "", fill=PEACH, line=RGBColor(0xF4, 0xB1, 0x83), radius=0.04)
txt(s, 4.75, 0.98, 6, 0.35, "Inner loop: wheel speed (each wheel)", size=14, color=ORANGE, bold=True)
box(s, 0.9, 4.25, 15.9, 1.55, "", fill=PANEL, line=None, radius=0.04)
txt(s, 1.0, 5.45, 6, 0.3, "Outer loop: trajectory", size=13, color=MUTED, bold=True)
txt(s, 0.0, y0 - 0.45, 1.2, 0.4, [("x*, y*, θ*", {})], size=14)
line(s, 0.0, y0, 1.12, y0, head=True)
summer(s, 1.4, y0)
txt(s, 1.0, y0 - 0.65, 0.3, 0.3, "+", size=14)
txt(s, 1.18, y0 + 0.3, 0.3, 0.3, "−", size=16)
line(s, 1.68, y0, 2.35, y0, head=True)
txt(s, 1.85, y0 - 0.4, 0.4, 0.3, "e", size=14, italic=True)
box(s, 2.35, y0 - 0.55, 1.75, 1.1, "P (SIMC)", sub=[("Kd, Ky, Kθ", {"italic": True})], fill=YELLOW, line=INK, size=15, sub_size=13)
line(s, 4.1, y0, 4.85, y0, head=True)
txt(s, 4.1, y0 - 0.45, 0.8, 0.3, "v*, ω*", size=13)
box(s, 4.85, y0 - 0.55, 1.75, 1.1, "Inverse", sub="kinematics", fill=WHITE, line=INK, size=15, sub_size=13)
line(s, 6.6, y0, 7.12, y0, head=True)
txt(s, 6.62, y0 - 0.45, 0.6, 0.3, [("v*", {}), ("L,R", {"sub": True})], size=13)
summer(s, 7.4, y0)
txt(s, 7.0, y0 - 0.65, 0.3, 0.3, "+", size=14)
txt(s, 7.18, y0 + 0.3, 0.3, 0.3, "−", size=16)
line(s, 7.68, y0, 8.25, y0, head=True)
txt(s, 7.78, y0 - 0.4, 0.4, 0.3, [("e", {"italic": True}), ("v", {"sub": True})], size=14)
box(s, 8.25, y0 - 0.55, 1.65, 1.1, "PI (S-L)", sub=[("C", {"italic": True}), ("v", {"sub": True, "italic": True}), ("(z)", {"italic": True})], fill=PINK, line=INK, size=15, sub_size=13)
line(s, 9.9, y0, 10.55, y0, head=True)
txt(s, 10.12, y0 - 0.4, 0.3, 0.3, "u", size=14, italic=True)
box(s, 10.55, y0 - 0.55, 2.0, 1.1, "Driver + motor", sub=[("G", {"italic": True}), ("m", {"sub": True, "italic": True}), ("(z)", {"italic": True})], fill=GREY, line=INK, size=15, sub_size=13)
txt(s, 9.7, 0.0, 4.2, 0.35, [("d", {"italic": True}), (": ramp, m·g·sin φ", {})], size=13, color=MUTED)
line(s, 11.55, 0.35, 11.55, y0 - 0.55, head=True, color=INK)
line(s, 12.55, y0, 13.35, y0, head=True)
txt(s, 12.65, y0 - 0.4, 0.6, 0.3, [("v", {"italic": True}), ("L,R", {"sub": True})], size=14)
box(s, 13.35, y0 - 0.55, 1.75, 1.1, "Forward", sub="kinematics", fill=GREY, line=INK, size=15, sub_size=13)
line(s, 15.1, y0, 16.7, y0, head=True)
txt(s, 15.3, y0 - 0.75, 1.4, 0.6, "pose (x, y, θ)", size=13)
box(s, 9.0, 2.95, 2.0, 0.85, "Encoder", sub=[("H(z) · 1440 CPR", {"italic": True})], fill=WHITE, line=INK, size=14, sub_size=12)
path(s, [(12.95, y0), (12.95, 3.37), (11.0, 3.37)], color=INK)
path(s, [(9.0, 3.37), (7.4, 3.37), (7.4, y0 + 0.28)], color=INK)
box(s, 6.6, 4.55, 2.3, 0.85, "Odometry", sub=[("estimated pose", {"italic": True})], fill=WHITE, line=INK, size=14, sub_size=12)
path(s, [(15.9, y0), (15.9, 4.97), (8.9, 4.97)], color=INK)
path(s, [(6.6, 4.97), (1.4, 4.97), (1.4, y0 + 0.28)], color=INK)

# =========================================================================== 4 ball-position control
s = new_slide()


def axis_chain(yc, a, cam_y, cam_side):
    txt(s, 0.0, yc - 0.5, 0.9, 0.4, [(a, {"italic": True}), ("des", {"sub": True})], size=15)
    line(s, 0.0, yc, 0.92, yc, head=True)
    summer(s, 1.2, yc)
    txt(s, 0.8, yc + (0.3 if cam_side < 0 else -0.65), 0.3, 0.3, "+", size=14)
    txt(s, 0.95, yc + (-0.68 if cam_side < 0 else 0.28), 0.3, 0.3, "−", size=16)
    line(s, 1.48, yc, 2.1, yc, head=True)
    txt(s, 1.6, yc - 0.42, 0.5, 0.3, [("e", {"italic": True}), (a, {"sub": True, "italic": True})], size=14)
    box(s, 2.1, yc - 0.55, 2.1, 1.1, "Controller", sub=[(a, {"italic": True})], fill=PINK, line=INK, size=15, sub_size=14)
    line(s, 4.2, yc, 4.92, yc, head=True)
    txt(s, 4.25, yc - 0.45, 0.8, 0.3, [("α", {"italic": True}), ("des," + a, {"sub": True})], size=14)
    summer(s, 5.2, yc)
    txt(s, 4.85, yc - 0.65 if cam_side > 0 else yc + 0.3, 0.3, 0.3, "+", size=14)
    line(s, 5.48, yc, 6.15, yc, head=True)
    box(s, 6.15, yc - 0.55, 1.75, 1.1, "Saturation", sub="±25°", fill=YELLOW, line=INK, size=15, sub_size=13)
    line(s, 7.9, yc, 8.45, yc, head=True)
    box(s, 8.45, yc - 0.55, 1.15, 1.1, "IK", fill=WHITE, line=INK, size=15)
    line(s, 9.6, yc, 10.35, yc, head=True)
    txt(s, 9.68, yc - 0.45, 0.7, 0.3, [("θ", {"italic": True}), ("m," + a, {"sub": True})], size=14)
    box(s, 10.35, yc - 0.55, 1.75, 1.1, "Servo", sub=[(a, {"italic": True})], fill=GREY, line=INK, size=15, sub_size=14)
    path(s, [(12.1, yc), (13.0, yc), (13.0, 3.6 + (-0.3 if cam_side > 0 else 0.3)), (13.75, 3.6 + (-0.3 if cam_side > 0 else 0.3))])
    box(s, 9.2, cam_y - 0.4, 2.6, 0.8, "Camera · " + a, fill=WHITE, line=INK, size=15)
    path(s, [(15.8, 3.6), (15.8, cam_y), (11.8, cam_y)], color=INK)
    path(s, [(9.2, cam_y), (1.2, cam_y), (1.2, yc + (0.28 if cam_side < 0 else -0.28))], color=INK)


axis_chain(1.9, "x", 0.6, +1)
axis_chain(5.3, "y", 6.6, -1)
box(s, 13.75, 2.9, 1.8, 1.4, "Plate", fill=GREY, line=INK, size=16)
line(s, 15.55, 3.6, 16.5, 3.6, head=True)
txt(s, 15.7, 3.1, 0.8, 0.4, [("x, y", {"italic": True})], size=15)
box(s, 4.2, 3.15, 2.0, 0.9, "Mobile base", sub=[("tilt φ", {"italic": True})], fill=GREENT, line=INK, size=14, sub_size=13)
line(s, 5.2, 3.15, 5.2, 1.9 + 0.28, head=True, color=INK)
line(s, 5.2, 4.05, 5.2, 5.3 - 0.28, head=True, color=INK)

out = os.path.join(HERE, "diagrams_en.pptx")
prs.save(out)
print("saved", out)
