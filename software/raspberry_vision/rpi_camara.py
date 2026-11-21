"""Camara Brio en la RPi: detecta la pelota y la manda al myRIO por UART.

Modos:
  local   (por defecto) La RPi detecta la pelota y la pasa al myRIO por UART.
          Con --laptop, ademas le manda a la laptop la posicion y una imagen
          cada --ver cuadros, solo para mirar y calibrar (laptop_vision.py).
  laptop  (mejora futura) La RPi manda el cuadro de 320x180 por UDP a la laptop,
          la laptop detecta y devuelve (x, y), y la RPi lo pasa al UART. Mide
          la latencia total (captura -> resultado) para compararla con local.

Uso:
  python3 rpi_camara.py --uart                                  # solo RPi -> myRIO
  python3 rpi_camara.py --uart --laptop 10.192.216.50           # + ver en la laptop
  python3 rpi_camara.py -t 30 --csv lat.csv                     # 30 s y guardar latencias
  python3 rpi_camara.py --modo laptop --laptop 10.192.216.50    # la laptop detecta
  python3 rpi_camara.py --modo laptop --laptop ... --crudo      # JPEG 1280x720 sin decodificar

UART (230400 8N1): <x,y,valido,seq>\\n con x, y en mm del plato si esta calibrado
(config_vision.json), si no en px de la imagen de 320x180.
"""
import argparse
import collections
import csv
import math
import multiprocessing as mp
import os
import queue
import socket
import statistics
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2
import numpy as np

from deteccion import (CUADRO, MAX_UDP, PUERTO_LAPTOP, PUERTO_RPI, RESULTADO, a_mm, canal,
                       cargar_config, detectar_ventana, escalar_cfg)

DEV = "/dev/video0"
PAGINA_VISTA = (b'<!doctype html><html><head><meta charset="utf-8"><title>Pelota</title></head>'
                b'<body style="background:#111;color:#ddd;font-family:sans-serif;margin:16px">'
                b'<h3>rpi_camara.py: lo que se detecta y se envia</h3>'
                b'<img src="/stream" style="max-width:100%"></body></html>')


class Vista:
    """Video para mirar en el navegador (--http PUERTO): la imagen que se procesa,
    la pelota detectada, su rastro y la posicion que sale por la UART.

    Corre en un PROCESO aparte y con menor prioridad (ver VistaProceso): con el
    video abierto en el mismo proceso la latencia subia de 27 a ~40 ms (3-nov).
    """

    def __init__(self, puerto, fps=15, clientes=None):
        self.lock = threading.Lock()
        self.dato = None
        self.rastro = collections.deque(maxlen=40)
        self.periodo = 1.0 / fps
        self.clientes = clientes   # mp.Value: cuantos navegadores miran (lo lee el lazo)
        vista = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_GET(self):
                if self.path == "/":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(PAGINA_VISTA)
                elif self.path.startswith("/stream"):
                    vista.servir(self)
                else:
                    self.send_error(404)

        servidor = ThreadingHTTPServer(("0.0.0.0", puerto), Handler)
        servidor.daemon_threads = True
        threading.Thread(target=servidor.serve_forever, daemon=True).start()

    def actualizar(self, jpeg, x, y, r, ok, lat, xm=float("nan"), ym=float("nan"), chico=None, det_cfg=None):
        # Se guarda el JPEG original de la camara: el video se decodifica aparte a
        # 640x360 (nitido), sin depender de la resolucion chica de la deteccion.
        with self.lock:
            self.dato = (jpeg, x, y, r, ok, lat, xm, ym, chico, det_cfg)
            if ok:
                self.rastro.append((x, y))

    def cuadro(self):
        with self.lock:
            if self.dato is None:
                return None
            jpeg, x, y, r, ok, lat, xm, ym, chico, det_cfg = self.dato
            rastro = list(self.rastro)
        vis = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_REDUCED_COLOR_2)
        if vis is None:
            return None
        e = 2   # x, y vienen en la escala de 320x180
        cv2.drawMarker(vis, (320, 180), (255, 0, 0), cv2.MARKER_CROSS, 20, 1)
        for (a, b), (c, d) in zip(rastro, rastro[1:]):
            cv2.line(vis, (int(a * e), int(b * e)), (int(c * e), int(d * e)), (0, 200, 0), 1)
        if ok:
            centro = (int(x * e), int(y * e))
            cv2.circle(vis, centro, int(r * e), (0, 255, 255), 2)
            cv2.drawMarker(vis, centro, (0, 0, 255), cv2.MARKER_CROSS, 14, 2)
            if xm == xm:   # calibrado: lo que sale por la UART esta en mm
                texto = f"X = {xm:+.1f}  Y = {ym:+.1f} mm   ({x:.1f}, {y:.1f} px)   {lat:.0f} ms"
            else:
                texto = f"x = {x:.1f}  y = {y:.1f} px  (r = {r:.1f})   latencia {lat:.0f} ms"
        else:
            texto = "sin pelota"
        cv2.putText(vis, texto, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        det = canal(chico, det_cfg) if chico is not None and det_cfg else None
        if det is not None:
            # Recuadro: lo que ve el detector = su canal gris (R-B o G-max(R,B)) y el umbral.
            gris, umbral, nombre = det
            m = cv2.threshold(gris, umbral - 1, 255, cv2.THRESH_BINARY)[1]
            g = cv2.cvtColor(gris, cv2.COLOR_GRAY2BGR)
            g[m > 0] = (0, 255, 0)
            g = cv2.resize(g, (192, 108), interpolation=cv2.INTER_NEAREST)
            vis[40:148, 640 - 196:640 - 4] = g
            cv2.rectangle(vis, (640 - 197, 39), (640 - 3, 149), (255, 255, 255), 1)
            cv2.putText(vis, f"{nombre} >= {umbral} (detector)", (640 - 196, 162),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
        return cv2.imencode(".jpg", vis, [cv2.IMWRITE_JPEG_QUALITY, 70])[1].tobytes()

    def servir(self, h):
        # Buffer de envio chico: si el WiFi no da abasto se saltan cuadros en vez
        # de acumularse (si no, el video se atrasa segundos).
        h.connection.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 32 * 1024)
        h.connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        h.send_response(200)
        h.send_header("Content-Type", "multipart/x-mixed-replace; boundary=cuadro")
        h.send_header("Cache-Control", "no-cache")
        h.end_headers()
        if self.clientes is not None:
            with self.clientes.get_lock():
                self.clientes.value += 1
        try:
            while True:
                t = time.monotonic()
                datos = self.cuadro()
                if datos:
                    h.wfile.write(b"--cuadro\r\nContent-Type: image/jpeg\r\n"
                                  b"Content-Length: %d\r\n\r\n" % len(datos))
                    h.wfile.write(datos)
                    h.wfile.write(b"\r\n")
                time.sleep(max(0.0, self.periodo - (time.monotonic() - t)))
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            if self.clientes is not None:
                with self.clientes.get_lock():
                    self.clientes.value -= 1


def _proceso_vista(puerto, fps, cola, clientes):
    os.nice(10)   # que nunca le quite CPU a la deteccion
    vista = Vista(puerto, fps, clientes)
    while True:
        vista.actualizar(*cola.get())


class VistaProceso:
    """Lo que usa el lazo de deteccion: manda el ultimo cuadro al proceso de la
    Vista solo si hay un navegador mirando y a lo sumo fps veces por segundo.
    Si el proceso esta ocupado, el cuadro se descarta (nunca bloquea)."""

    def __init__(self, puerto, fps=15):
        ctx = mp.get_context("fork")
        self.cola = ctx.Queue(maxsize=1)
        self.clientes = ctx.Value("i", 0)
        self.periodo = 1.0 / fps
        self.t_ult = 0.0
        ctx.Process(target=_proceso_vista, args=(puerto, fps, self.cola, self.clientes),
                    daemon=True).start()

    def actualizar(self, *dato):
        ahora = time.monotonic()
        if self.clientes.value <= 0 or ahora - self.t_ult < self.periodo:
            return
        self.t_ult = ahora
        try:
            self.cola.put_nowait(dato)
        except queue.Full:
            pass


def configurar_camara(a):
    ctrls = [
        "zoom_absolute=100", "pan_absolute=0", "tilt_absolute=0",
        "focus_automatic_continuous=0", f"focus_absolute={a.focus}",
        "auto_exposure=1",                       # 1 = manual
        "exposure_dynamic_framerate=0",          # que no baje los fps con poca luz
        f"exposure_time_absolute={a.exp}",
        f"gain={a.gain}",
        "white_balance_automatic=0",             # color estable para el umbral
        f"white_balance_temperature={a.wb}",
        f"saturation={a.sat}",
        "backlight_compensation=0",
        "power_line_frequency=2",                # 60 Hz (Peru)
    ]
    for c in ctrls:
        subprocess.run(["v4l2-ctl", "-d", DEV, "-c", c], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def abrir_camara():
    cap = cv2.VideoCapture(DEV, cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    cap.set(cv2.CAP_PROP_FPS, 60)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 2)   # con 1 se pierde la mitad de los cuadros
    cap.set(cv2.CAP_PROP_CONVERT_RGB, 0)  # entrega el JPEG crudo
    return cap


class Camara:
    """Lee la camara en un hilo y guarda solo el ultimo cuadro: nunca se procesa
    un cuadro viejo mientras hay uno nuevo esperando."""

    def __init__(self):
        self.cap = abrir_camara()
        if not self.cap.isOpened():
            raise SystemExit("No se pudo abrir la camara (/dev/video0)")
        self.jpeg, self.t_cap, self.n = None, 0.0, 0
        self.cond = threading.Condition()
        self.activo = True
        self.hilo = threading.Thread(target=self._leer, daemon=True)
        self.hilo.start()

    def cerrar(self):
        """Detiene el hilo antes de soltar la camara (si no, OpenCV aborta al salir)."""
        self.activo = False
        self.hilo.join(timeout=1.0)
        self.cap.release()

    def _leer(self):
        while self.activo:
            ok, buf = self.cap.read()
            if not ok:
                continue
            # Marca de tiempo del buffer V4L2 (CLOCK_MONOTONIC, igual que time.monotonic).
            t = self.cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
            with self.cond:
                self.jpeg, self.t_cap = buf.tobytes(), t if t > 0 else time.monotonic()
                self.n += 1
                self.cond.notify_all()

    def siguiente(self, visto):
        with self.cond:
            self.cond.wait_for(lambda: self.n > visto, timeout=2.0)
            return self.jpeg, self.t_cap, self.n


class Estadisticas:
    def __init__(self, ruta_csv):
        self.lock = threading.Lock()
        self.lat, self.n_cap, self.n_env, self.n_res, self.n_ok, self.grandes = [], 0, 0, 0, 0, 0
        self.bytes = 0
        self.t0 = time.monotonic()
        self.csv = None
        if ruta_csv:
            self.f = open(ruta_csv, "w", newline="")
            self.csv = csv.writer(self.f)
            self.csv.writerow(["t_s", "seq", "x_px", "y_px", "x_mm", "y_mm", "valido",
                               "lat_ms", "proc_ms"])

    def resultado(self, seq, t_cap, x, y, xm, ym, ok, proc_ms):
        lat = (time.monotonic() - t_cap) * 1000
        with self.lock:
            self.lat.append(lat)
            self.n_res += 1
            self.n_ok += ok
            if self.csv:
                self.csv.writerow([f"{time.monotonic() - self.t0:.3f}", seq, f"{x:.2f}", f"{y:.2f}",
                                   f"{xm:.1f}", f"{ym:.1f}", int(ok), f"{lat:.1f}", f"{proc_ms:.2f}"])

    def imprimir(self, dt, modo):
        with self.lock:
            lat, self.lat = self.lat, []
            n = (self.n_cap, self.n_env, self.n_res, self.n_ok, self.grandes, self.bytes)
            self.n_cap = self.n_env = self.n_res = self.n_ok = self.grandes = self.bytes = 0
        cap, env, res, ok, grandes, b = n
        txt = f"camara {cap / dt:5.1f} fps | "
        if modo == "laptop":
            txt += f"enviados {env / dt:5.1f}/s ({b / dt / 1e6 * 8:4.1f} Mbit/s) | "
        txt += f"resultados {res / dt:5.1f}/s, pelota {ok}/{res}"
        if lat:
            lat.sort()
            txt += f" | latencia mediana {statistics.median(lat):5.1f} ms, p95 {lat[int(0.95 * (len(lat) - 1))]:5.1f} ms"
        if grandes:
            txt += f" | {grandes} cuadros > 64 KB descartados"
        txt += estado_cpu()
        print(txt, flush=True)


def estado_cpu():
    """Temperatura y MHz de la CPU: sobre ~80 C la RPi 3 baja la frecuencia y la
    latencia sube (3-nov: 27 ms frio, 36-45 ms caliente)."""
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            temp = int(f.read()) / 1000
        with open("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq") as f:
            mhz = int(f.read()) // 1000
    except (OSError, ValueError):
        return ""
    return f" | CPU {temp:.0f} C {mhz} MHz" + ("  << CALIENTE: ventilar la RPi" if temp >= 80 else "")


def enviar_uart(ser, x, y, xm, ym, ok, seq):
    if ser is None:
        return
    if not math.isnan(xm):
        x, y = xm, ym
    try:
        ser.write(f"<{x:.1f},{y:.1f},{int(ok)},{seq}>\n".encode())
    except Exception:  # buffer lleno: se pierde esta trama, no se bloquea
        pass


def recibir_resultados(sock, est, ser):
    """Modo laptop: recibe (x, y) de la laptop, lo pasa al UART y mide la latencia."""
    while True:
        try:
            datos, _ = sock.recvfrom(256)
        except OSError:
            return
        if len(datos) != RESULTADO.size:
            continue
        magic, seq, t_cap, x, y, xm, ym, ok, proc = RESULTADO.unpack(datos)
        if magic != b"RSLT":
            continue
        enviar_uart(ser, x, y, xm, ym, ok, seq)
        est.resultado(seq, t_cap, x, y, xm, ym, ok, proc)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--laptop", help="IP de la laptop (para mirar/calibrar; obligatoria en modo laptop)")
    ap.add_argument("--modo", choices=["local", "laptop"], default="local")
    ap.add_argument("--crudo", action="store_true",
                    help="modo laptop: mandar el JPEG 1280x720 de la camara sin decodificar")
    # 31-oct, en la RPi: 1/8 -> latencia 25.6 ms (1/4: 28.9 ms), pelota quieta tiembla
    # 0.13-0.17 px (1/4: 0.05-0.10 px). Las dos detectan 60/60 cuadros.
    ap.add_argument("--reducir", type=int, choices=[4, 8], default=8,
                    help="modo local: decodificar a 1/8 (160x90, por defecto) o 1/4 (320x180, "
                         "algo mas precisa y ~3 ms mas lenta). Las coordenadas salen siempre "
                         "en la escala de 320x180")
    ap.add_argument("--calidad", type=int, default=80, help="calidad JPEG del cuadro de 320x180")
    ap.add_argument("--ver", type=int, default=6,
                    help="modo local: mandar una imagen cada N cuadros (0 = nunca)")
    ap.add_argument("--http", type=int, metavar="PUERTO",
                    help="ver la deteccion en el navegador (ej. --http 8090 y el tunel ssh -L)")
    ap.add_argument("--uart", nargs="?", const="/dev/serial0", default=None)
    # 230400 (2-nov): ~1 ms por trama. Main.vi del myRIO tiene que estar a la misma velocidad.
    ap.add_argument("--baud", type=int, default=230400)
    ap.add_argument("-t", "--segundos", type=float, default=0, help="0 = hasta Ctrl+C")
    ap.add_argument("--csv", help="guardar cada resultado y su latencia")
    # 2-nov: 4 ms con ganancia 200 da el mismo brillo que 8.3 ms / 100, sin parpadeo
    # (variacion entre cuadros 0.6 %), y la mitad de estela con la pelota rapida.
    ap.add_argument("--exp", type=int, default=40, help="exposicion en 100 us (40 = 4 ms)")
    ap.add_argument("--gain", type=int, default=60,
                    help="ganancia (12-nov: 200 quemaba la pelota con luz de dia; 60 = circulo completo)")
    ap.add_argument("--focus", type=int, default=30)
    ap.add_argument("--wb", type=int, default=5500, help="balance de blancos [K] (5500 = luz de dia; 4000 la ponia azul)")
    ap.add_argument("--sat", type=int, default=160, help="saturacion de la camara")
    a = ap.parse_args()
    if a.modo == "laptop" and not a.laptop:
        ap.error("el modo laptop necesita --laptop IP")

    cfg = cargar_config()
    # La vista se crea primero: el fork no debe heredar la camara ni la UART.
    vista = VistaProceso(a.http) if a.http else None
    ser = None
    if a.uart:
        import serial
        ser = serial.Serial(a.uart, a.baud, timeout=0, write_timeout=0)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", PUERTO_RPI))
    destino = (a.laptop, PUERTO_LAPTOP) if a.laptop else None
    est = Estadisticas(a.csv)
    if a.modo == "laptop":
        threading.Thread(target=recibir_resultados, args=(sock, est, ser), daemon=True).start()

    configurar_camara(a)
    cam = Camara()
    print(f"Modo {a.modo}"
          f"{f' | laptop {a.laptop}:{PUERTO_LAPTOP}' if a.laptop else ' | sin laptop'}"
          f"{' (JPEG crudo 1280x720)' if a.crudo else ''}"
          f"{' | UART ' + a.uart if a.uart else ''}"
          f" | {'calibrado en mm' if cfg.get('homografia') else 'sin calibrar: px'}"
          f" | detecta en {1280 // a.reducir}x{720 // a.reducir}")

    # Deteccion a 1/8: radios y contorno del plato a la mitad, y el resultado se
    # multiplica por k para entregarlo en la escala de 320x180 (la de la calibracion).
    k = a.reducir // 4
    cfg_det = cfg if k == 1 else escalar_cfg(cfg, 1 / k)
    flag = cv2.IMREAD_REDUCED_COLOR_4 if k == 1 else cv2.IMREAD_REDUCED_COLOR_8
    previo = None   # ultima deteccion (en px de la imagen decodificada)
    if vista:
        print(f"Video en http://localhost:{a.http} (con ssh -L {a.http}:localhost:{a.http})")

    visto, t_ini = 0, time.monotonic()
    t_imp = t_ini
    try:
        while not a.segundos or time.monotonic() - t_ini < a.segundos:
            jpeg, t_cap, n = cam.siguiente(visto)
            if jpeg is None or n == visto:
                continue
            with est.lock:
                est.n_cap += n - visto
            visto = n

            if a.modo == "laptop":
                if a.crudo:
                    datos, reducir = jpeg, 4
                else:
                    img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_REDUCED_COLOR_4)
                    if img is None:
                        continue
                    datos = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, a.calidad])[1].tobytes()
                    reducir = 1
                if len(datos) > MAX_UDP:
                    with est.lock:
                        est.grandes += 1
                    continue
                sock.sendto(CUADRO.pack(b"CUAD", n, t_cap, 1, reducir) + datos, destino)
                with est.lock:
                    est.n_env += 1
                    est.bytes += len(datos)
            else:
                t1 = time.monotonic()
                img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), flag)
                if img is None:
                    continue
                x, y, r, ok, _ = detectar_ventana(img, cfg_det, previo)
                previo = (x, y, r) if ok else None
                # Cada pixel decodificado es el promedio de un bloque de 4k x 4k
                # pixeles: su centro esta (4k - 1) / 2 px mas alla de su esquina.
                # Pasado a la escala de 320x180 (dividir entre 4): + (4k - 1) / 8.
                x, y, r = x * k + (4 * k - 1) / 8, y * k + (4 * k - 1) / 8, r * k
                xm, ym = a_mm(x, y, cfg) if ok else (float("nan"), float("nan"))
                proc = (time.monotonic() - t1) * 1000
                enviar_uart(ser, x, y, xm, ym, ok, n)
                est.resultado(n, t_cap, x, y, xm, ym, ok, proc)
                if vista:
                    vista.actualizar(jpeg, x, y, r, ok, (time.monotonic() - t_cap) * 1000, xm, ym,
                                     img, {k: cfg[k] for k in ("filtro", "rb_min", "verde_min") if k in cfg})
                if destino:   # solo para mirar en la laptop
                    sock.sendto(RESULTADO.pack(b"TELE", n, t_cap, x, y, xm, ym, ok, proc), destino)
                if destino and a.ver and n % a.ver == 0:
                    if k != 1:   # la laptop espera 320x180
                        img = cv2.resize(img, None, fx=k, fy=k, interpolation=cv2.INTER_NEAREST)
                    datos = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 70])[1].tobytes()
                    sock.sendto(CUADRO.pack(b"CUAD", n, t_cap, 0, 1) + datos, destino)

            ahora = time.monotonic()
            if ahora - t_imp >= 1.0:
                est.imprimir(ahora - t_imp, a.modo)
                t_imp = ahora
    except KeyboardInterrupt:
        pass
    finally:
        cam.cerrar()
        sock.close()
        if est.csv:
            est.f.close()


if __name__ == "__main__":
    main()
