"""Barrido de enfoque de la Brio: encuentra el focus_absolute mas nitido.

Para cada valor de enfoque toma un cuadro de 1280x720, mide la nitidez
(varianza del Laplaciano en la zona central) y guarda la foto. Al final dice
cual fue el mejor y deja la camara en ese valor.

Uso (en la RPi):
  python3 foco_camara.py                      # 0 a 150 de 10 en 10
  python3 foco_camara.py --desde 20 --hasta 60 --paso 5
Fotos en ~/vision/fotos_foco/ (foco_XXX.jpg).
"""
import argparse
import os
import subprocess
import time
from types import SimpleNamespace

import cv2
import numpy as np

from rpi_camara import DEV, abrir_camara, configurar_camara

CARPETA = os.path.expanduser("~/vision/fotos_foco")


def cuadro(cap, descartar=12):
    """Descarta cuadros viejos del buffer y devuelve uno nuevo decodificado."""
    for _ in range(descartar):
        cap.read()
    ok, buf = cap.read()
    return cv2.imdecode(np.frombuffer(buf, np.uint8), cv2.IMREAD_COLOR) if ok else None


def nitidez(img):
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = g.shape
    zona = g[h // 4: 3 * h // 4, w // 4: 3 * w // 4]   # centro: donde esta el plato
    return cv2.Laplacian(zona, cv2.CV_64F).var()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--desde", type=int, default=0)
    ap.add_argument("--hasta", type=int, default=150)
    ap.add_argument("--paso", type=int, default=10)
    ap.add_argument("--exp", type=int, default=83)
    ap.add_argument("--gain", type=int, default=100)
    a = ap.parse_args()

    os.makedirs(CARPETA, exist_ok=True)
    configurar_camara(SimpleNamespace(exp=a.exp, gain=a.gain, focus=a.desde, wb=4000, sat=160))
    cap = abrir_camara()
    if not cap.isOpened():
        raise SystemExit("No se pudo abrir la camara")

    resultados = []
    for f in range(a.desde, a.hasta + 1, a.paso):
        subprocess.run(["v4l2-ctl", "-d", DEV, "-c", f"focus_absolute={f}"], check=False)
        time.sleep(0.6)   # que el lente llegue
        img = cuadro(cap)
        if img is None:
            continue
        n = nitidez(img)
        resultados.append((f, n))
        cv2.imwrite(os.path.join(CARPETA, f"foco_{f:03d}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 90])
        print(f"focus {f:3d}: nitidez {n:8.1f}", flush=True)

    mejor = max(resultados, key=lambda r: r[1])
    subprocess.run(["v4l2-ctl", "-d", DEV, "-c", f"focus_absolute={mejor[0]}"], check=False)
    cap.release()
    print(f"\nMEJOR: focus {mejor[0]} (nitidez {mejor[1]:.1f}). Usar --focus {mejor[0]} en rpi_camara.py")
    print(f"Fotos en {CARPETA}")


if __name__ == "__main__":
    main()
