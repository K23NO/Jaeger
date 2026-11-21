"""Calibracion px -> mm a partir de las 4 esquinas del plato.

1. Encuentra el plato (oscuro sobre fondo claro) y sus 4 esquinas.
2. Homografia: esquinas en px (imagen de 320x180) -> esquinas en mm, con el
   origen en el centro del plato.
      X = ancho del plato (lado corto, --ancho), Y = largo (lado largo, --largo).
      Por defecto Y crece hacia la derecha de la imagen y X hacia abajo, que con
      Z hacia la camara es un sistema derecho. --invertir-x / --invertir-y.
3. Corrige la altura de la pelota: su centro esta un radio sobre el plato, y
   vista desde arriba aparece mas lejos del centro de la imagen. Se escala
   respecto al centro de la imagen por (Z - r) / Z, con Z = altura de la camara
   (estimada del tamano del plato en la imagen y el campo de vision de la Brio).
4. Guarda la homografia y el contorno del plato en config_vision.json.

Uso:
  python3 calibrar_esquinas.py                       # captura de la camara (en la RPi)
  python3 calibrar_esquinas.py --imagen foto.jpg     # o desde una foto de 1280x720
  python3 calibrar_esquinas.py --diametro 40 --largo 231 --ancho 175
Guarda calib_esquinas.jpg con lo encontrado para revisarlo.
"""
import argparse
import math
import os

import cv2
import numpy as np

from deteccion import cargar_config, guardar_config

HFOV_GRADOS = 82.1   # Brio con zoom 100 (campo diagonal de 90 grados), imagen 16:9
ESCALA = 4           # 1280x720 -> 320x180 (la escala de las coordenadas)


def capturar(focus):
    from types import SimpleNamespace
    from rpi_camara import abrir_camara, configurar_camara
    configurar_camara(SimpleNamespace(exp=83, gain=100, focus=focus, wb=4000, sat=160))
    cap = abrir_camara()
    for _ in range(40):
        cap.read()
    _, buf = cap.read()
    cap.release()
    return cv2.imdecode(np.frombuffer(buf, np.uint8), cv2.IMREAD_COLOR)


def esquinas_plato(img, umbral):
    """Las 4 esquinas del plato en px de la imagen completa, ordenadas
    arriba-izq, arriba-der, abajo-der, abajo-izq."""
    g = cv2.GaussianBlur(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (5, 5), 0)
    oscuro = (g < umbral).astype(np.uint8) * 255
    # Cerrar los huecos (pelota, piezas encima) y separar lo que toca el borde.
    oscuro = cv2.morphologyEx(oscuro, cv2.MORPH_CLOSE, np.ones((41, 41), np.uint8))
    oscuro = cv2.morphologyEx(oscuro, cv2.MORPH_OPEN, np.ones((15, 15), np.uint8))
    cnts, _ = cv2.findContours(oscuro, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    h, w = g.shape
    candidatos = []
    for c in cnts:
        area = cv2.contourArea(c)
        if area < 0.10 * h * w:
            continue
        casco = cv2.convexHull(c)
        for eps in np.linspace(0.01, 0.08, 15):
            aprox = cv2.approxPolyDP(casco, eps * cv2.arcLength(casco, True), True)
            if len(aprox) == 4:
                candidatos.append((area, aprox.reshape(4, 2).astype(np.float32), c))
                break
    if not candidatos:
        raise SystemExit("No se encontro un plato de 4 lados (probar otro --umbral)")
    _, quad, contorno = max(candidatos, key=lambda t: t[0])
    quad = refinar(contorno, quad)
    # Ordenar: arriba-izq (x+y minimo), abajo-der (maximo), arriba-der, abajo-izq.
    s, d = quad.sum(axis=1), quad[:, 0] - quad[:, 1]
    return np.array([quad[s.argmin()], quad[d.argmax()], quad[s.argmax()], quad[d.argmin()]],
                    np.float32)


def refinar(contorno, quad):
    """Ajusta una recta a los puntos del contorno de cada lado y toma las
    intersecciones: esquinas con precision de subpixel."""
    pts = contorno.reshape(-1, 2).astype(np.float32)
    rectas = []
    for i in range(4):
        a, b = quad[i], quad[(i + 1) % 4]
        ab = b - a
        largo = np.linalg.norm(ab)
        t = ((pts - a) @ ab) / largo ** 2
        dist = np.abs(ab[0] * (pts[:, 1] - a[1]) - ab[1] * (pts[:, 0] - a[0])) / largo
        lado = pts[(t > 0.15) & (t < 0.85) & (dist < 8)]
        vx, vy, x0, y0 = cv2.fitLine(lado, cv2.DIST_HUBER, 0, 0.01, 0.01).ravel()
        rectas.append((np.array([x0, y0]), np.array([vx, vy])))
    salida = []
    for i in range(4):
        (p1, d1), (p2, d2) = rectas[i - 1], rectas[i]
        t = np.linalg.solve(np.column_stack([d1, -d2]), p2 - p1)[0]
        salida.append(p1 + t * d1)
    return np.array(salida, np.float32)


def afinar_bordes(img, quad, buscar=20, muestras=60):
    """Esquinas aproximadas -> esquinas precisas. En cada lado toma puntos a lo
    largo, busca sobre la perpendicular (+-buscar px) donde cambia mas el gris
    (el borde del plato), ajusta una recta y corta las rectas vecinas."""
    g = cv2.GaussianBlur(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (5, 5), 0).astype(np.float32)
    centro = quad.mean(axis=0)
    rectas, puntos_borde = [], []
    for i in range(4):
        a, b = quad[i], quad[(i + 1) % 4]
        d = (b - a) / np.linalg.norm(b - a)
        n = np.array([-d[1], d[0]])
        if np.dot(n, centro - a) > 0:
            n = -n                               # normal hacia afuera del plato
        pts = []
        for t in np.linspace(0.12, 0.88, muestras):
            p = a + t * (b - a)
            s = np.arange(-buscar, buscar + 0.5, 0.5, dtype=np.float32)
            mx = (p[0] + s * n[0]).reshape(1, -1).astype(np.float32)
            my = (p[1] + s * n[1]).reshape(1, -1).astype(np.float32)
            perfil = cv2.remap(g, mx, my, cv2.INTER_LINEAR).ravel()
            # Desde adentro del plato hacia afuera: el borde es el PRIMER punto
            # donde deja de ser oscuro (lo que hay mas alla, cables o piezas, no
            # cuenta). Se toma el cruce a mitad de camino entre el gris del plato
            # y el de afuera, con interpolacion lineal.
            # Sirve si afuera es mas claro (mesa) o mas oscuro (fondo negro).
            nivel = float(np.median(perfil[:10]))
            cambio = np.nonzero(np.abs(perfil - nivel) > 15)[0]
            if len(cambio) == 0 or cambio[0] < 10:
                continue
            k = int(cambio[0])
            afuera = float(perfil[min(k + 4, len(perfil) - 1)])
            medio = (nivel + afuera) / 2
            signo = 1.0 if afuera > nivel else -1.0
            j = k
            while j > 0 and signo * (perfil[j - 1] - medio) > 0:
                j -= 1
            v0, v1 = perfil[j - 1], perfil[j]
            frac = (medio - v0) / (v1 - v0) if v1 != v0 else 0.0
            pts.append(p + (s[j - 1] + 0.5 * frac) * n)
        pts = np.array(pts, np.float32)
        # Ajuste robusto: recta, descartar puntos lejanos (> 1.5 px), volver a ajustar.
        usar = pts
        for _ in range(3):
            vx, vy, x0, y0 = cv2.fitLine(usar, cv2.DIST_HUBER, 0, 0.01, 0.01).ravel()
            dist_todos = np.abs(vx * (pts[:, 1] - y0) - vy * (pts[:, 0] - x0))
            nuevos = pts[dist_todos < 1.5]
            if len(nuevos) < 8:
                break
            usar = nuevos
        rectas.append((np.array([x0, y0]), np.array([vx, vy])))
        puntos_borde.append(usar)
        # Calidad: distancia de los puntos usados a la recta. Un borde limpio da < 1 px.
        pts = usar
        dist = np.abs(vx * (pts[:, 1] - y0) - vy * (pts[:, 0] - x0))
        nombre = ("arriba", "derecha", "abajo", "izquierda")[i]
        aviso = "" if np.median(dist) < 1.0 and len(pts) >= 15 else \
            "   <-- REVISAR: algo tapa o se cruza con este borde"
        print(f"Borde {nombre:9s}: {len(pts):2d}/{muestras} puntos, desvio mediano "
              f"{np.median(dist):.2f} px, p90 {np.percentile(dist, 90):.2f} px{aviso}")
    salida = []
    for i in range(4):
        (p1, d1), (p2, d2) = rectas[i - 1], rectas[i]
        t = np.linalg.solve(np.column_stack([d1, -d2]), p2 - p1)[0]
        salida.append(p1 + t * d1)
    return np.array(salida, np.float32), puntos_borde


def escala_centro(s, c):
    """Matriz que escala por s respecto al punto c."""
    return np.array([[s, 0, c[0] * (1 - s)], [0, s, c[1] * (1 - s)], [0, 0, 1]], np.float64)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--imagen", help="foto de 1280x720 (si no, captura de la camara)")
    ap.add_argument("--largo", type=float, default=231.0, help="lado largo del plato = Y [mm]")
    ap.add_argument("--ancho", type=float, default=175.0, help="lado corto del plato = X [mm]")
    ap.add_argument("--diametro", type=float, default=40.0, help="diametro de la pelota [mm]")
    ap.add_argument("--umbral", type=int, default=50, help="gris maximo del plato (0-255)")
    ap.add_argument("--esquinas", help="esquinas aproximadas en px de 1280x720, en orden "
                    "arriba-izq;arriba-der;abajo-der;abajo-izq. Ej: 330,115;965,83;975,567;357,582. "
                    "Se afinan solas sobre el borde. Sin esto se buscan automaticamente")
    ap.add_argument("--buscar", type=int, default=20,
                    help="px a cada lado de la recta aproximada donde se busca el borde "
                         "(bajarlo si hay otro borde oscuro cerca, ej. una placa detras)")
    ap.add_argument("--focus", type=int, default=20)
    ap.add_argument("--invertir-x", action="store_true")
    ap.add_argument("--invertir-y", action="store_true")
    ap.add_argument("--no-guardar", action="store_true")
    a = ap.parse_args()

    img = cv2.imread(a.imagen) if a.imagen else capturar(a.focus)
    if img is None or img.shape[:2] != (720, 1280):
        raise SystemExit("Hace falta una imagen de 1280x720")

    bordes = []
    if a.esquinas:
        aprox = np.array([[float(v) for v in p.split(",")] for p in a.esquinas.split(";")], np.float32)
        esq, bordes = afinar_bordes(img, aprox, buscar=a.buscar)   # px de 1280x720
    else:
        esq = esquinas_plato(img, a.umbral)
    esq320 = esq / ESCALA
    hx, hy = a.ancho / 2, a.largo / 2
    sx = -1 if a.invertir_x else 1
    sy = -1 if a.invertir_y else 1
    # arriba-izq, arriba-der, abajo-der, abajo-izq -> (X, Y) en mm
    mm = np.array([[-sx * hx, -sy * hy], [-sx * hx, sy * hy],
                   [sx * hx, sy * hy], [sx * hx, -sy * hy]], np.float32)
    H_plato = cv2.getPerspectiveTransform(esq320, mm).astype(np.float64)

    # Altura de la camara: Z = f * tamano real / tamano en px (promedio de los 4 lados).
    f320 = (1280 / ESCALA / 2) / math.tan(math.radians(HFOV_GRADOS / 2))
    lados_px = [np.linalg.norm(esq320[(i + 1) % 4] - esq320[i]) for i in range(4)]
    lados_mm = [a.largo, a.ancho, a.largo, a.ancho]
    Z = float(np.mean([f320 * L / p for L, p in zip(lados_mm, lados_px)]))
    r = a.diametro / 2
    c = np.array([159.5, 89.5])                     # centro de la imagen de 320x180
    S = escala_centro((Z - r) / Z, c)                # centro de la pelota -> punto del plato debajo
    H = H_plato @ S
    H /= H[2, 2]

    # Contorno para buscar la pelota: el plato visto a la altura del centro de la
    # pelota (r) + 4 px. Ajustado a proposito: si se agranda mas, entran objetos
    # de color que estan junto al plato (31-oct: una caja amarilla al costado).
    crece = Z / (Z - r)
    roi = c + (esq320 - c) * crece
    roi = c + (roi - c) * (1 + 4 / np.linalg.norm(roi - c, axis=1, keepdims=True))

    print(f"Esquinas (px 1280x720): " + "  ".join(f"({x:.1f}, {y:.1f})" for x, y in esq))
    print(f"Lados en px (320x180): " + ", ".join(f"{p:.1f}" for p in lados_px))
    print(f"Altura estimada de la camara: {Z:.0f} mm | escala en el centro: "
          f"{a.largo / np.mean(lados_px[0::2]):.2f} mm/px (320x180)")
    print(f"Correccion por la altura de la pelota (r = {r:.0f} mm): x {(Z - r) / Z:.4f}")
    print(f"Ejes: +X hacia {'arriba' if a.invertir_x else 'abajo'} de la imagen, "
          f"+Y hacia la {'izquierda' if a.invertir_y else 'derecha'}")

    # Imagen de revision
    vis = img.copy()
    for pts in bordes:
        for p in pts:
            cv2.circle(vis, (int(round(p[0])), int(round(p[1]))), 2, (0, 165, 255), -1)
    cv2.polylines(vis, [np.round(esq).astype(np.int32)], True, (0, 255, 0), 1)
    cv2.polylines(vis, [np.round(roi * ESCALA).astype(np.int32)], True, (255, 255, 0), 1)
    Hi = np.linalg.inv(H_plato)
    for (p, q, color, nombre) in (((0, 0), (40, 0), (0, 0, 255), "+X"), ((0, 0), (0, 40), (255, 0, 0), "+Y")):
        pp = cv2.perspectiveTransform(np.array([[p, q]], np.float32), Hi)[0] * ESCALA
        cv2.arrowedLine(vis, tuple(map(int, pp[0])), tuple(map(int, pp[1])), color, 3, tipLength=0.25)
        cv2.putText(vis, nombre, tuple(map(int, pp[1] + 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2)
    for (x, y), (X, Y) in zip(esq, mm):
        cv2.putText(vis, f"({X:+.1f}, {Y:+.1f})", (int(x) - 70, int(y) + (-12 if y < 360 else 28)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    cv2.imwrite("calib_esquinas.jpg", vis)
    print("Imagen de revision: calib_esquinas.jpg")

    if not a.no_guardar:
        cfg = cargar_config()
        cfg["homografia"] = H.tolist()
        cfg["roi_px"] = [[round(float(x), 1), round(float(y), 1)] for x, y in roi]
        cfg["calibracion"] = {"metodo": "esquinas", "largo_mm": a.largo, "ancho_mm": a.ancho,
                              "diametro_mm": a.diametro, "altura_camara_mm": round(Z, 1),
                              "invertir_x": a.invertir_x, "invertir_y": a.invertir_y}
        guardar_config(cfg)
        print("Guardado en config_vision.json")


if __name__ == "__main__":
    main()
