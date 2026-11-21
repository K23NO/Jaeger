"""Video en vivo de la Logitech Brio para verla desde la laptop.

Corre en la RPi y sirve un stream MJPEG por HTTP:
  - normal: la imagen de 320x180 que usa la deteccion (ampliada x2), con la
    pelota detectada, el centro de la imagen y la mascara al lado.
  - --crudo: la imagen de la camara sin deteccion, a 640x360 (para encuadrar).
    Con --completo va el JPEG de 1280x720 tal cual (pesado para el WiFi).

Uso (desde la laptop, una sola linea; Ctrl+C lo detiene):
  ssh -t -L 8090:localhost:8090 rpi-ballplate "cd ~/pruebas && python3 stream_camara.py"
y abrir http://localhost:8090 en el navegador. (En la laptop el 8080 esta ocupado.)

Otras opciones:
  python3 stream_camara.py --crudo --fps 10
  python3 stream_camara.py --exp 150 --gain 100 --focus 20 --rmin 10 --rmax 20
  http://localhost:8090/foto   -> una foto de 1280x720 (clic derecho, guardar)

La conexion tiene un buffer de envio chico: si el WiFi no da abasto se saltan
cuadros en vez de acumularse, asi la imagen no se atrasa.

Necesita vision_ball.py en la misma carpeta.
"""
import argparse
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2
import numpy as np

from vision_ball import COLORES, R_MAX, R_MIN, abrir_camara, configurar_camara, detectar

PAGINA = """<!doctype html>
<html><head><meta charset="utf-8"><title>Camara del plato</title>
<style>
body {{ background: #111; color: #ddd; font-family: sans-serif; margin: 16px; }}
img {{ max-width: 100%; }}
a {{ color: #8cf; }}
</style></head>
<body>
<h3>Camara del plato ({modo})</h3>
<img src="/stream">
<p><a href="/foto">Foto 1280x720</a></p>
</body></html>
"""


class Camara:
    """Lee la camara en un hilo a 60 fps y guarda el ultimo JPEG."""

    def __init__(self):
        self.cap = abrir_camara()
        if not self.cap.isOpened():
            raise SystemExit("No se pudo abrir la camara (/dev/video0)")
        self.jpeg = None
        self.n = 0
        self.fps = 0.0
        self.cond = threading.Condition()
        threading.Thread(target=self._leer, daemon=True).start()

    def _leer(self):
        t0, n0 = time.monotonic(), 0
        while True:
            ok, buf = self.cap.read()
            if not ok:
                continue
            with self.cond:
                self.jpeg = buf.tobytes()
                self.n += 1
                self.cond.notify_all()
            ahora = time.monotonic()
            if ahora - t0 >= 1.0:
                self.fps = (self.n - n0) / (ahora - t0)
                t0, n0 = ahora, self.n

    def ultimo(self, visto):
        """Espera un cuadro mas nuevo que `visto`; devuelve (jpeg, numero)."""
        with self.cond:
            self.cond.wait_for(lambda: self.n > visto, timeout=2.0)
            return self.jpeg, self.n


def vista_cruda(jpeg):
    """Cuadro a 640x360 con una cruz en el centro, para encuadrar."""
    img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_REDUCED_COLOR_2)
    if img is None:
        return None
    h, w = img.shape[:2]
    cv2.drawMarker(img, (w // 2, h // 2), (0, 0, 255), cv2.MARKER_CROSS, 30, 1)
    _, enc = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 70])
    return enc.tobytes()


def vista_deteccion(jpeg, args, lo, hi, fps):
    img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_REDUCED_COLOR_4)
    if img is None:  # cuadro MJPEG danado
        return None
    x, y, r, ok, mask = detectar(img, lo, hi, args.rmin, args.rmax)

    vis = cv2.resize(img, None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST)
    h, w = vis.shape[:2]
    cv2.drawMarker(vis, (w // 2, h // 2), (255, 0, 0), cv2.MARKER_CROSS, 20, 1)
    if ok:
        cv2.circle(vis, (int(2 * x), int(2 * y)), int(2 * r), (0, 0, 255), 2)
        cv2.drawMarker(vis, (int(2 * x), int(2 * y)), (0, 0, 255), cv2.MARKER_CROSS, 12, 2)
    texto = f"{'OK' if ok else '--'}  x={x:.1f} y={y:.1f} r={r:.1f} px  |  camara {fps:.0f} fps"
    cv2.putText(vis, texto, (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2)

    m = cv2.resize(mask, (w, h), interpolation=cv2.INTER_NEAREST)
    salida = np.hstack([vis, cv2.cvtColor(m, cv2.COLOR_GRAY2BGR)])
    _, enc = cv2.imencode(".jpg", salida, [cv2.IMWRITE_JPEG_QUALITY, 75])
    return enc.tobytes()


def crear_handler(cam, args, lo, hi):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def enviar(self, tipo, datos):
            self.send_response(200)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(datos)))
            self.end_headers()
            self.wfile.write(datos)

        def do_GET(self):
            if self.path == "/":
                modo = ("1280x720 completo" if args.completo else "640x360 sin deteccion"
                        if args.crudo else "deteccion 320x180 + mascara")
                self.enviar("text/html; charset=utf-8", PAGINA.format(modo=modo).encode())
            elif self.path.startswith("/foto"):
                jpeg, _ = cam.ultimo(0)
                if jpeg is None:
                    self.send_error(503, "La camara todavia no entrega cuadros")
                else:
                    self.enviar("image/jpeg", jpeg)
            elif self.path.startswith("/stream"):
                self.stream()
            else:
                self.send_error(404)

        def stream(self):
            # Buffer de envio chico: a lo mas ~1 cuadro en camino. Con el buffer
            # normal (MB) el WiFi lento acumulaba segundos de video atrasado.
            self.connection.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 32 * 1024)
            self.connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=cuadro")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            visto = 0
            periodo = 1.0 / args.fps
            try:
                while True:
                    t = time.monotonic()
                    jpeg, visto = cam.ultimo(visto)
                    if jpeg is None:
                        continue
                    if args.completo:
                        datos = jpeg
                    elif args.crudo:
                        datos = vista_cruda(jpeg)
                    else:
                        datos = vista_deteccion(jpeg, args, lo, hi, cam.fps)
                    if datos is None:
                        continue
                    self.wfile.write(b"--cuadro\r\nContent-Type: image/jpeg\r\n"
                                     b"Content-Length: %d\r\n\r\n" % len(datos))
                    self.wfile.write(datos)
                    self.wfile.write(b"\r\n")
                    time.sleep(max(0.0, periodo - (time.monotonic() - t)))
            except (BrokenPipeError, ConnectionResetError):
                pass  # se cerro el navegador

    return Handler


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--puerto", type=int, default=8090)
    ap.add_argument("--fps", type=float, default=10, help="cuadros por segundo del stream")
    ap.add_argument("--crudo", action="store_true", help="imagen sin deteccion, a 640x360")
    ap.add_argument("--completo", action="store_true", help="JPEG de 1280x720 tal cual (pesado)")
    ap.add_argument("--exp", type=int, default=100, help="exposicion en unidades de 100 us")
    ap.add_argument("--gain", type=int, default=128)
    ap.add_argument("--focus", type=int, default=0)
    ap.add_argument("--color", choices=COLORES, default="negro")
    ap.add_argument("--rmin", type=float, default=R_MIN, help="radio minimo de la pelota [px]")
    ap.add_argument("--rmax", type=float, default=R_MAX, help="radio maximo de la pelota [px]")
    args = ap.parse_args()

    lo, hi = COLORES[args.color]
    configurar_camara(args.exp, args.gain, args.focus)
    cam = Camara()

    servidor = ThreadingHTTPServer(("0.0.0.0", args.puerto), crear_handler(cam, args, lo, hi))
    servidor.daemon_threads = True
    print(f"Stream en http://localhost:{args.puerto}  (con el tunel ssh -L)")
    print(f"      o en http://{socket.gethostname()}.local:{args.puerto}  (misma red WiFi)")
    print("Ctrl+C para salir")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        servidor.server_close()
        cam.cap.release()


if __name__ == "__main__":
    main()
