"""Deteccion de la pelota de color sobre el plato negro (lo usan la RPi y la laptop).

La pelota es de un color fuerte y el plato es negro mate. Filtros (cfg["filtro"]):
  "verde"  pelota verde fosforescente (desde el 10-nov): un canal G - B donde G > R.
  "rb"     pelota naranja/roja: un canal R - B.
  otro     HSV con saturacion y brillo altos (los reflejos blancos quedan fuera).

Tambien define el formato de los paquetes UDP entre la RPi y la laptop y la
configuracion compartida (config_vision.json).
"""
import json
import math
import os
import struct

import cv2
import numpy as np

CONFIG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config_vision.json")

# Imagen de trabajo: 1280x720 de la camara reducida 1/4 al decodificar.
ANCHO, ALTO = 320, 180

POR_DEFECTO = {
    # Umbral de color en HSV de OpenCV (H 0-179, S y V 0-255).
    "s_min": 110,       # saturacion minima: separa la pelota del negro y de los reflejos
    "v_min": 80,        # brillo minimo
    "h_min": 0,         # tono; con h_min > h_max el rango cruza el rojo (ej. 170 -> 10)
    "h_max": 179,       # 0-179 = cualquier color
    # Filtro de un canal: rojo - azul. Una pelota naranja/roja sobre un plato
    # negro o azulado da R-B alto; la mesa blanca, el gris y los reflejos dan ~0.
    # (2-nov: pelota p5 = 82, todo lo demas <= 84 incluido un brazo.) 0 = apagado.
    "rb_min": 70,
    # Filtro "verde" (10-nov, pelota verde fosforescente; la rampa del robot tiene
    # piezas naranjas): un canal "gris" = G - B, puesto en 0 donde G no supera a R.
    # La Brio ve la pelota verde-amarilla: G-B ~142, G-R ~18 (siempre > 0). Naranja,
    # rojo y piel tienen G < R (G-R ~ -99) -> 0; blanco/gris/plato negro -> ~0.
    # Un gris de brillo normal no sirve: el naranja tambien es brillante.
    "verde_min": 60,     # umbral de G - B (pelota p10 = 91, fondo <= 8)
    "verde_gr_min": 1,   # G - R minimo (separa el verde-amarillo del naranja)
    "g_canal_min": 80,   # y el canal G por lo menos asi de brillante
    # Forma, en px de la imagen de 320x180.
    "r_min": 6.0,
    "r_max": 40.0,
    "circ_min": 0.65,   # 4*pi*A/P^2 (circulo = 1)
    "llenado_min": 0.65,  # area / area del circulo envolvente (circulo ~1)
    # px -> mm en el plato (de laptop_vision.py --calibrar-plato). None = sin calibrar.
    "homografia": None,
    # Contorno del plato en px (de --calibrar-plato): fuera de el no se busca la pelota.
    "roi_px": None,
}

# ---------------- Paquetes UDP ----------------
# RPi -> laptop: cabecera + JPEG.
#   magic, seq, t_captura [s, reloj de la RPi], responder (1 = la laptop detecta y
#   responde; 0 = solo para ver), reducir (4 = JPEG de 1280x720 que hay que reducir)
CUADRO = struct.Struct("<4sIdBB")
# laptop -> RPi (RSLT) y RPi -> laptop en modo local (TELE):
#   magic, seq, t_captura (eco), x_px, y_px, x_mm, y_mm, valido, ms de procesamiento
RESULTADO = struct.Struct("<4sIdffffBf")
PUERTO_LAPTOP = 5005
PUERTO_RPI = 5006
MAX_UDP = 65000


def cargar_config(ruta=None):
    # La ruta se lee al llamar (no al importar), para que una prueba pueda
    # cambiar deteccion.CONFIG sin tocar el archivo real.
    ruta = ruta or CONFIG
    cfg = dict(POR_DEFECTO)
    if os.path.exists(ruta):
        with open(ruta) as f:
            cfg.update(json.load(f))
    return cfg


def guardar_config(cfg, ruta=None):
    with open(ruta or CONFIG, "w") as f:
        json.dump(cfg, f, indent=2)


KERNEL = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
_roi_cache = {}


def mascara_roi(cfg, forma):
    """Mascara del plato (255 adentro); None si no esta calibrado."""
    roi = cfg.get("roi_px")
    if not roi:
        return None
    clave = (tuple(map(tuple, roi)), forma)
    if clave not in _roi_cache:
        m = np.zeros(forma, np.uint8)
        cv2.fillPoly(m, [np.round(np.array(roi)).astype(np.int32)], 255)
        _roi_cache[clave] = m
    return _roi_cache[clave]


def canal(img, cfg):
    """Imagen de un canal (como un gris) que usa el detector, su umbral y su nombre.
    None si el filtro es HSV. img en BGR."""
    filtro = cfg.get("filtro")
    if filtro == "rb":
        return cv2.subtract(img[:, :, 2], img[:, :, 0]), int(cfg.get("rb_min", 70)), "R-B"
    if filtro == "verde":
        b, g, r = cv2.split(img)
        gris = cv2.subtract(g, b)
        no_verde = cv2.subtract(g, r) < int(cfg.get("verde_gr_min", 1))   # naranja, rojo, piel
        gris[no_verde] = 0
        return gris, int(cfg.get("verde_min", 60)), "G-B (G>R)"
    return None


def mascara(img, cfg, roi=None):
    filtro = cfg.get("filtro")
    if filtro in ("rb", "verde"):
        # Sin HSV: solo canales (rb: pelota roja/naranja; verde: pelota verde).
        # Medido en la RPi a 160x90: 0.26 ms frente a 0.32 ms del HSV.
        gris, umbral, _ = canal(img, cfg)
        m = cv2.threshold(gris, umbral - 1, 255, cv2.THRESH_BINARY)[1]
        if filtro == "rb":
            brillo, minimo = img[:, :, 2], int(cfg.get("r_canal_min", 120))
        else:
            brillo, minimo = img[:, :, 1], int(cfg.get("g_canal_min", 100))
        m &= cv2.threshold(brillo, minimo - 1, 255, cv2.THRESH_BINARY)[1]
        return cv2.morphologyEx(m, cv2.MORPH_OPEN, KERNEL)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    s, v = int(cfg["s_min"]), int(cfg["v_min"])
    h1, h2 = int(cfg["h_min"]), int(cfg["h_max"])
    if h1 <= h2:
        m = cv2.inRange(hsv, (h1, s, v), (h2, 255, 255))
    else:  # rango que cruza el rojo: h1..179 y 0..h2
        m = cv2.inRange(hsv, (h1, s, v), (179, 255, 255)) | cv2.inRange(hsv, (0, s, v), (h2, 255, 255))
    rb_min = int(cfg.get("rb_min", 0))
    if rb_min > 0:   # ademas del color, el contraste rojo - azul (un canal, como un gris)
        rb = cv2.subtract(img[:, :, 2], img[:, :, 0])
        m &= cv2.threshold(rb, rb_min - 1, 255, cv2.THRESH_BINARY)[1]
    return cv2.morphologyEx(m, cv2.MORPH_OPEN, KERNEL)


def detectar(img, cfg, ventana=None):
    """Devuelve (x, y, r, valido, mascara) en px de img.

    Entre las manchas del color buscado elige la mas grande que parezca un circulo.
    ventana = (x0, y0, x1, y1): buscar solo en ese recuadro (las coordenadas
    devueltas siguen siendo de la imagen completa).
    """
    # El contorno del plato NO recorta la mascara (cerca del borde cortaba la pelota,
    # que en la imagen asoma por fuera): se usa para descartar manchas cuyo centro
    # cae fuera del plato.
    contorno = np.array(cfg["roi_px"], np.float32) if cfg.get("roi_px") else None
    x0 = y0 = 0
    if ventana is not None:
        x0, y0, x1, y1 = ventana
        img = img[y0:y1, x0:x1]
    m = mascara(img, cfg)
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    mejor, mejor_area = None, 0.0
    for c in cnts:
        area = cv2.contourArea(c)
        if area <= mejor_area:
            continue
        (_, _), r = cv2.minEnclosingCircle(c)
        if not cfg["r_min"] <= r <= cfg["r_max"]:
            continue
        per = cv2.arcLength(c, True)
        if per == 0 or 4 * math.pi * area / per ** 2 < cfg["circ_min"]:
            continue
        if area / (math.pi * r * r) < cfg["llenado_min"]:
            continue
        if contorno is not None:
            mo = cv2.moments(c)
            centro = (mo["m10"] / mo["m00"] + x0, mo["m01"] / mo["m00"] + y0)
            if cv2.pointPolygonTest(contorno, centro, False) < 0:
                continue
        mejor, mejor_area = c, area
    if mejor is None:
        return 0.0, 0.0, 0.0, False, m
    mo = cv2.moments(mejor)
    (_, _), r = cv2.minEnclosingCircle(mejor)
    return mo["m10"] / mo["m00"] + x0, mo["m01"] / mo["m00"] + y0, r, True, m


def escalar_cfg(cfg, f):
    """Configuracion para detectar en una imagen f veces mas chica (ej. f = 0.5
    para 160x90): escala los radios y el contorno del plato."""
    c = dict(cfg, r_min=cfg["r_min"] * f, r_max=cfg["r_max"] * f)
    if cfg.get("roi_px"):
        c["roi_px"] = [[x * f, y * f] for x, y in cfg["roi_px"]]
    return c


def detectar_ventana(img, cfg, previo):
    """Como detectar(), pero si se conoce la posicion anterior previo = (x, y, r)
    busca primero en un recuadro alrededor (unas 10 veces menos pixeles). Si ahi
    no esta, busca en toda la imagen."""
    if previo is not None:
        x, y, r = previo
        medio = int(2 * r + 16)   # la pelota se mueve < 16 px por cuadro a 60 fps
        h, w = img.shape[:2]
        ventana = (max(int(x) - medio, 0), max(int(y) - medio, 0),
                   min(int(x) + medio, w), min(int(y) + medio, h))
        res = detectar(img, cfg, ventana)
        if res[3]:
            return res
    return detectar(img, cfg)


def a_mm(x, y, cfg):
    """px (imagen de 320x180) -> mm en el plato. nan si no hay calibracion."""
    H = cfg.get("homografia")
    if H is None:
        return float("nan"), float("nan")
    p = np.asarray(H) @ np.array([x, y, 1.0])
    return float(p[0] / p[2]), float(p[1] / p[2])


def dibujar(img, x, y, r, ok, cfg, escala=1):
    """Dibuja la deteccion y los ejes del plato (si esta calibrado) sobre img."""
    h, w = img.shape[:2]
    cv2.drawMarker(img, (w // 2, h // 2), (255, 0, 0), cv2.MARKER_CROSS, 10 * escala, 1)
    if cfg.get("roi_px"):
        roi = (np.array(cfg["roi_px"]) * escala).astype(np.int32)
        cv2.polylines(img, [roi], True, (255, 255, 0), 1)
    H = cfg.get("homografia")
    if H is not None:
        Hi = np.linalg.inv(np.asarray(H))
        for a, b, color in (((-100, 0), (100, 0), (0, 0, 200)), ((0, -100), (0, 100), (0, 200, 0))):
            pts = cv2.perspectiveTransform(np.array([[a, b]], np.float32), Hi)[0] * escala
            cv2.line(img, tuple(map(int, pts[0])), tuple(map(int, pts[1])), color, 1)
    if ok:
        c = (int(x * escala), int(y * escala))
        cv2.circle(img, c, int(r * escala), (0, 255, 255), 2)
        cv2.drawMarker(img, c, (0, 255, 255), cv2.MARKER_CROSS, 8 * escala, 2)
