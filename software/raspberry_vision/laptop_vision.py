"""Laptop: mira y calibra la camara de la RPi (y, como mejora, detecta por UDP).

Con la RPi en modo local (el normal), muestra lo que la RPi detecto y sirve para
calibrar. Con la RPi en modo laptop (mejora futura), detecta y le devuelve
(x, y) a la RPi apenas termina, antes de dibujar.

Uso:
  python laptop_vision.py                     # mostrar (y responder en modo laptop)
  python laptop_vision.py --sin-ventana       # sin ventana: lo minimo de latencia
  python laptop_vision.py --csv detec.csv     # guardar cada deteccion
  python laptop_vision.py --calibrar-color    # ajustar el umbral de color con barras
  python laptop_vision.py --calibrar-plato --dx 80 --dy 60 --ancho 228 --alto 175
                                              # pelota en 9 marcas conocidas -> px a mm
Teclas: q = salir. En calibracion: g = guardar, espacio = tomar punto.
La configuracion queda en config_vision.json (copiarla a la RPi para el modo local).
"""
import argparse
import csv
import socket
import time

import cv2
import numpy as np

from deteccion import (CONFIG, CUADRO, PUERTO_LAPTOP, PUERTO_RPI, RESULTADO, a_mm, cargar_config,
                       detectar, dibujar, guardar_config)

NAN = float("nan")


def abrir_socket(puerto):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1 << 20)
    if hasattr(socket, "SIO_UDP_CONNRESET"):
        # Windows: que un "puerto inalcanzable" de la RPi no rompa el recvfrom.
        s.ioctl(socket.SIO_UDP_CONNRESET, False)
    s.bind(("0.0.0.0", puerto))
    s.settimeout(0.5)
    return s


def recibir(sock):
    """Espera un paquete y vacia la cola. Devuelve el cuadro (CUAD) mas nuevo con
    su remitente y la ultima telemetria (TELE): los cuadros viejos se descartan."""
    try:
        paquetes = [sock.recvfrom(70000)]
    except (socket.timeout, ConnectionResetError):
        return None, None
    sock.setblocking(False)
    try:
        while True:
            paquetes.append(sock.recvfrom(70000))
    except OSError:
        pass
    sock.settimeout(0.5)
    cuadro = tele = None
    for datos, remitente in paquetes:
        if datos[:4] == b"CUAD" and len(datos) > CUADRO.size:
            cuadro = (datos, remitente)
        elif datos[:4] == b"TELE" and len(datos) == RESULTADO.size:
            tele = RESULTADO.unpack(datos)
    return cuadro, tele


def procesar(datos, cfg):
    _, seq, t_cap, responder, reducir = CUADRO.unpack_from(datos)
    t1 = time.perf_counter()
    flag = cv2.IMREAD_REDUCED_COLOR_4 if reducir == 4 else cv2.IMREAD_COLOR
    img = cv2.imdecode(np.frombuffer(datos, np.uint8, offset=CUADRO.size), flag)
    if img is None:
        return None
    x, y, r, ok, m = detectar(img, cfg)
    xm, ym = a_mm(x, y, cfg) if ok else (NAN, NAN)
    proc = (time.perf_counter() - t1) * 1000
    return dict(seq=seq, t_cap=t_cap, responder=responder, img=img, mask=m,
                x=x, y=y, r=r, ok=ok, xm=xm, ym=ym, proc=proc)


def responder(sock, d, remitente):
    sock.sendto(RESULTADO.pack(b"RSLT", d["seq"], d["t_cap"], d["x"], d["y"], d["xm"], d["ym"],
                               d["ok"], d["proc"]), (remitente[0], PUERTO_RPI))


def vista(d, cfg, texto, con_mascara=True):
    vis = cv2.resize(d["img"], None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST)
    dibujar(vis, d["x"], d["y"], d["r"], d["ok"], cfg, escala=2)
    for i, linea in enumerate(texto.split("\n")):
        cv2.putText(vis, linea, (8, 22 + 22 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2)
    if not con_mascara:
        return vis
    m = cv2.resize(d["mask"], (vis.shape[1], vis.shape[0]), interpolation=cv2.INTER_NEAREST)
    return np.hstack([vis, cv2.cvtColor(m, cv2.COLOR_GRAY2BGR)])


def texto_deteccion(d):
    if not d["ok"]:
        return "-- sin pelota"
    t = f"x={d['x']:.1f} y={d['y']:.1f} r={d['r']:.1f} px"
    if d["xm"] == d["xm"]:
        t += f"  |  {d['xm']:+.1f}, {d['ym']:+.1f} mm"
    return t


# ---------------- Modo normal ----------------
def correr(sock, cfg, args):
    log = None
    if args.csv:
        f = open(args.csv, "w", newline="")
        log = csv.writer(f)
        log.writerow(["t_s", "seq", "x_px", "y_px", "r_px", "x_mm", "y_mm", "valido", "proc_ms"])
    t0 = t_imp = time.monotonic()
    n, n_ok, proc, ultimo, tele = 0, 0, 0.0, None, None
    print(f"Esperando cuadros en el puerto UDP {PUERTO_LAPTOP}... (q para salir)")
    while True:
        cuadro, t = recibir(sock)
        tele = t or tele
        if cuadro:
            d = procesar(cuadro[0], cfg)
            if d:
                if d["responder"]:
                    responder(sock, d, cuadro[1])   # primero responder, despues dibujar
                n += 1
                n_ok += d["ok"]
                proc += d["proc"]
                ultimo = d
                if log:
                    log.writerow([f"{time.monotonic() - t0:.3f}", d["seq"], f"{d['x']:.2f}",
                                  f"{d['y']:.2f}", f"{d['r']:.1f}", f"{d['xm']:.1f}",
                                  f"{d['ym']:.1f}", int(d["ok"]), f"{d['proc']:.2f}"])
        ahora = time.monotonic()
        if ahora - t_imp >= 1.0:
            if n:
                print(f"{n / (ahora - t_imp):5.1f} cuadros/s | pelota {n_ok}/{n} | "
                      f"procesar {proc / n:4.1f} ms", flush=True)
            n, n_ok, proc, t_imp = 0, 0, 0.0, ahora
        if args.sin_ventana or ultimo is None:
            continue
        if ultimo["responder"]:
            texto = "Modo laptop: detecta la laptop\n" + texto_deteccion(ultimo)
        elif tele:
            _, seq, _, x, y, xm, ym, ok, p = tele
            ultimo.update(x=x, y=y, ok=ok, xm=xm, ym=ym, r=ultimo["r"])
            texto = f"Modo local: detecta la RPi ({p:.1f} ms)\n" + texto_deteccion(ultimo)
        else:
            texto = texto_deteccion(ultimo)
        cv2.imshow("Camara del plato", vista(ultimo, cfg, texto))
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break


# ---------------- Calibracion del color ----------------
BARRAS = [("s_min", 255), ("v_min", 255), ("h_min", 179), ("h_max", 179), ("r_min", 60), ("r_max", 90)]


def calibrar_color(sock, cfg):
    cv2.namedWindow("Ajustes", cv2.WINDOW_NORMAL)
    for nombre, maximo in BARRAS:
        cv2.createTrackbar(nombre, "Ajustes", int(cfg[nombre]), maximo, lambda _: None)
    print("Mueve las barras hasta que en la mascara SOLO quede la pelota (blanca).")
    print("Prueba la pelota en el centro, en las esquinas y con el plato inclinado.")
    print("g = guardar en config_vision.json, q = salir sin guardar")
    ultimo = None
    while True:
        cuadro, _ = recibir(sock)
        for nombre, _ in BARRAS:
            cfg[nombre] = cv2.getTrackbarPos(nombre, "Ajustes")
        if cuadro:
            ultimo = cuadro
        if ultimo:
            d = procesar(ultimo[0], cfg)
            if d:
                if d["responder"]:
                    responder(sock, d, ultimo[1])
                cv2.imshow("Camara del plato", vista(d, cfg, texto_deteccion(d)))
        k = cv2.waitKey(1) & 0xFF
        if k == ord("g"):
            guardar_config(cfg)
            print(f"Guardado en {CONFIG}: " + ", ".join(f"{n}={cfg[n]}" for n, _ in BARRAS))
        elif k == ord("q"):
            break


# ---------------- Calibracion px -> mm ----------------
def calibrar_plato(sock, cfg, dx, dy, ancho, alto):
    # 9 marcas en el plato, en mm desde el centro, con los ejes X/Y del plato.
    puntos_mm = [(0, 0), (dx, 0), (dx, dy), (0, dy), (-dx, dy),
                 (-dx, 0), (-dx, -dy), (0, -dy), (dx, -dy)]
    cfg["homografia"] = None   # mientras se calibra, mostrar en px y buscar en toda la imagen
    cfg["roi_px"] = None
    puntos_px = []
    muestras, tomando, ultimo = [], False, None
    print(f"Marca 9 puntos en el plato: centro, (+-{dx}, 0), (0, +-{dy}) y (+-{dx}, +-{dy}) mm.")
    print("Pon la pelota en cada uno y presiona ESPACIO (se promedian 20 detecciones).")
    while len(puntos_px) < len(puntos_mm):
        cuadro, _ = recibir(sock)
        if cuadro:
            d = procesar(cuadro[0], cfg)
            if d:
                if d["responder"]:
                    responder(sock, d, cuadro[1])
                ultimo = d
                if tomando and d["ok"]:
                    muestras.append((d["x"], d["y"]))
                    if len(muestras) >= 20:
                        px = np.mean(muestras, axis=0)
                        puntos_px.append(px)
                        print(f"  punto {len(puntos_px)}: {puntos_mm[len(puntos_px) - 1]} mm "
                              f"-> ({px[0]:.2f}, {px[1]:.2f}) px")
                        muestras, tomando = [], False
        if ultimo and len(puntos_px) < len(puntos_mm):
            k = len(puntos_px)
            texto = (f"Punto {k + 1}/9: pelota en {puntos_mm[k]} mm y ESPACIO\n"
                     + ("tomando..." if tomando else texto_deteccion(ultimo)))
            vis = vista(ultimo, cfg, texto, con_mascara=False)
            for p in puntos_px:
                cv2.drawMarker(vis, (int(2 * p[0]), int(2 * p[1])), (0, 0, 255), cv2.MARKER_TILTED_CROSS, 14, 2)
            cv2.imshow("Camara del plato", vis)
        tecla = cv2.waitKey(1) & 0xFF
        if tecla == ord(" ") and ultimo is not None:
            tomando, muestras = True, []
        elif tecla == ord("q"):
            print("Calibracion cancelada (no se guardo nada)")
            return

    src = np.array(puntos_px, np.float32)
    dst = np.array(puntos_mm, np.float32)
    H, _ = cv2.findHomography(src, dst, 0)   # minimos cuadrados con los 9 puntos
    cfg["homografia"] = H.tolist()
    err = [np.hypot(*(np.array(a_mm(p[0], p[1], cfg)) - q)) for p, q in zip(src, dst)]
    escala = np.hypot(*(np.array(a_mm(160, 90, cfg)) - np.array(a_mm(161, 90, cfg))))
    print(f"Error por punto [mm]: {', '.join(f'{e:.1f}' for e in err)}  (max {max(err):.1f})")
    print(f"Escala en el centro: {escala:.2f} mm/px")

    # Contorno del plato (+10 mm de margen por la inclinacion) -> solo se busca adentro.
    mx, my = ancho / 2 + 10, alto / 2 + 10
    esquinas = np.array([[[-mx, -my], [mx, -my], [mx, my], [-mx, my]]], np.float32)
    roi = cv2.perspectiveTransform(esquinas, np.linalg.inv(H))[0]
    cfg["roi_px"] = [[round(float(x), 1), round(float(y), 1)] for x, y in roi]
    guardar_config(cfg)
    print(f"Guardado en {CONFIG}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sin-ventana", action="store_true")
    ap.add_argument("--csv")
    ap.add_argument("--calibrar-color", action="store_true")
    ap.add_argument("--calibrar-plato", action="store_true")
    ap.add_argument("--dx", type=float, default=80, help="marcas en X: +-dx mm")
    ap.add_argument("--dy", type=float, default=60, help="marcas en Y: +-dy mm")
    ap.add_argument("--ancho", type=float, default=228, help="largo del plato en X [mm]")
    ap.add_argument("--alto", type=float, default=175, help="largo del plato en Y [mm]")
    args = ap.parse_args()

    cfg = cargar_config()
    sock = abrir_socket(PUERTO_LAPTOP)
    try:
        if args.calibrar_color:
            calibrar_color(sock, cfg)
        elif args.calibrar_plato:
            calibrar_plato(sock, cfg, args.dx, args.dy, args.ancho, args.alto)
        else:
            correr(sock, cfg, args)
    except KeyboardInterrupt:
        pass
    finally:
        sock.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
