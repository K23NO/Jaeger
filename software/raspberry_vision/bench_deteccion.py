"""Mide cuanto tarda cada etapa de la deteccion con la camara real.

Etapas: decodificar el JPEG (a 1/4 = 320x180 y a 1/8 = 160x90) y detectar la
pelota (imagen completa o ventana alrededor de la ultima posicion). Guarda una
imagen con la deteccion y la mascara para revisar que encuentra la pelota.

Uso (en la RPi, con la pelota sobre el plato):
  python3 bench_deteccion.py              # 300 cuadros
  python3 bench_deteccion.py -n 600 --focus 20
"""
import argparse
import os
import time
from types import SimpleNamespace

import cv2
import numpy as np

from deteccion import cargar_config, detectar, detectar_ventana, dibujar
from rpi_camara import abrir_camara, configurar_camara


def stats(v):
    v = sorted(v)
    return f"mediana {v[len(v) // 2]:5.2f} ms | p95 {v[int(0.95 * (len(v) - 1))]:5.2f} ms"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=300)
    ap.add_argument("--focus", type=int, default=20)
    ap.add_argument("--exp", type=int, default=83)
    ap.add_argument("--gain", type=int, default=100)
    a = ap.parse_args()

    cfg = cargar_config()
    configurar_camara(SimpleNamespace(exp=a.exp, gain=a.gain, focus=a.focus, wb=4000, sat=160))
    cap = abrir_camara()
    for _ in range(30):
        cap.read()

    t = {k: [] for k in ("dec4", "dec8", "det4", "det8", "ven4")}
    ok4 = ok8 = okv = 0
    ultimo4 = None
    ultimo = None
    for i in range(a.n):
        _, buf = cap.read()
        arr = np.frombuffer(buf, np.uint8)
        t0 = time.perf_counter()
        img4 = cv2.imdecode(arr, cv2.IMREAD_REDUCED_COLOR_4)
        t1 = time.perf_counter()
        img8 = cv2.imdecode(arr, cv2.IMREAD_REDUCED_COLOR_8)
        t2 = time.perf_counter()
        if img4 is None or img8 is None:
            continue
        r4 = detectar(img4, cfg)
        t3 = time.perf_counter()
        cfg8 = dict(cfg, r_min=cfg["r_min"] / 2, r_max=cfg["r_max"] / 2, roi_px=None)
        r8 = detectar(img8, cfg8)
        t4 = time.perf_counter()
        rv = detectar_ventana(img4, cfg, ultimo4)
        t5 = time.perf_counter()
        t["dec4"].append((t1 - t0) * 1000)
        t["dec8"].append((t2 - t1) * 1000)
        t["det4"].append((t3 - t2) * 1000)
        t["det8"].append((t4 - t3) * 1000)
        t["ven4"].append((t5 - t4) * 1000)
        ok4 += r4[3]
        ok8 += r8[3]
        okv += rv[3]
        ultimo4 = (rv[0], rv[1], rv[2]) if rv[3] else None
        ultimo = (img4, r4)

    n = len(t["dec4"])
    print(f"{n} cuadros")
    print(f"decodificar 320x180: {stats(t['dec4'])}")
    print(f"decodificar 160x90 : {stats(t['dec8'])}")
    print(f"detectar 320x180   : {stats(t['det4'])}   pelota {ok4}/{n}")
    print(f"detectar 160x90    : {stats(t['det8'])}   pelota {ok8}/{n}")
    print(f"detectar ventana   : {stats(t['ven4'])}   pelota {okv}/{n}")

    img, (x, y, r, ok, m) = ultimo
    vis = cv2.resize(img, None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST)
    dibujar(vis, x, y, r, ok, cfg, escala=2)
    cv2.putText(vis, f"{'OK' if ok else '--'} x={x:.1f} y={y:.1f} r={r:.1f}", (8, 22),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
    m2 = cv2.resize(m, (vis.shape[1], vis.shape[0]), interpolation=cv2.INTER_NEAREST)
    salida = os.path.expanduser("~/vision/bench_deteccion.jpg")
    cv2.imwrite(salida, np.hstack([vis, cv2.cvtColor(m2, cv2.COLOR_GRAY2BGR)]))
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    if ok:
        px = hsv[int(y), int(x)]
        print(f"color en el centro de la pelota (H, S, V): {tuple(int(v) for v in px)}")
    fondo = hsv[hsv.shape[0] // 2 - 20: hsv.shape[0] // 2 + 20, 40:80].reshape(-1, 3)
    print(f"plato (H, S, V) mediana: {tuple(int(v) for v in np.median(fondo, axis=0))}")
    print(f"Imagen: {salida}")
    cap.release()


if __name__ == "__main__":
    main()
