"""Captura el ensayo de la base movil (Lecturas.ino) y lo guarda en CSV.

El Arduino manda una linea CSV cada 20 ms. Este script le envia el comando
de inicio, recibe las lineas y las guarda en datos/planta_<...>.csv.

Modos (--modo):
  trayectoria  reposo 0.5 s -> avanzar 3 s -> girar 2 s -> detenido 1 s
  adelante     reposo 0.5 s -> ambas ruedas adelante 3 s -> detenido 1 s
  atras        reposo 0.5 s -> ambas ruedas atras 3 s -> detenido 1 s
  giro         reposo 0.5 s -> girar en su propio eje 3 s (hacia --giro) -> detenido 1 s

Uso:
  pip install pyserial matplotlib
  python capturar_planta.py                          # trayectoria, PWM 120, giro derecha
  python capturar_planta.py --puerto COM5 --pwm 150 --giro I --tipo M
  python capturar_planta.py --modo adelante --pwm 150 --graficar
  python capturar_planta.py --modo giro --giro I --pwm 150 --graficar
  python capturar_planta.py --repeticiones 3 --graficar

Cerrar el Monitor Serie del IDE de Arduino antes de correrlo: el puerto
solo puede abrirlo un programa a la vez.
"""
import argparse
import datetime
import os
import sys
import time

import serial
from serial.tools import list_ports

CARPETA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "datos")
TS_MS = 20
MODOS = {"trayectoria": "T", "adelante": "A", "atras": "B", "giro": "G"}


def buscar_puerto():
    puertos = list(list_ports.comports())
    for p in puertos:
        texto = f"{p.description} {p.manufacturer or ''}".lower()
        if any(k in texto for k in ("arduino", "ch340", "cp210", "usb serial", "usb-serial")):
            return p.device
    if len(puertos) == 1:
        return puertos[0].device
    print("Puertos disponibles:")
    for p in puertos:
        print(f"  {p.device}  {p.description}")
    sys.exit("No se pudo elegir el puerto: usa --puerto COMx")


def leer_linea(ser):
    return ser.readline().decode(errors="replace").strip()


def esperar_listo(ser, timeout=5.0):
    """Al abrir el puerto el Arduino se reinicia; esperar a que diga LISTO."""
    fin = time.time() + timeout
    while time.time() < fin:
        linea = leer_linea(ser)
        if linea:
            print(linea)
        if linea.startswith("# LISTO"):
            return
    print("Aviso: no llego '# LISTO'; se envia el comando de todos modos.")


def correr_ensayo(ser, args):
    """Devuelve (encabezado, filas) de un ensayo."""
    ser.reset_input_buffer()
    ser.write(f"S,{args.pwm},{args.giro},{args.tipo},{MODOS[args.modo]}\n".encode())

    encabezado = None
    filas = []
    malas = 0
    fin = time.time() + 20.0

    while time.time() < fin:
        linea = leer_linea(ser)
        if not linea:
            continue
        if linea.startswith("#"):
            print(linea)
            if linea.startswith("# FIN"):
                break
            continue
        if encabezado is None:
            encabezado = linea
            continue
        if linea.count(",") == encabezado.count(","):
            filas.append(linea)
        else:
            malas += 1
    else:
        sys.exit("No llego '# FIN' en 20 s. Revisa el puerto y que el sketch sea Lecturas.ino.")

    if encabezado is None:
        sys.exit("No llegaron datos.")

    # Muestras perdidas o atrasadas.
    tiempos = [int(f.split(",")[0]) for f in filas]
    saltos = sum(1 for a, b in zip(tiempos, tiempos[1:]) if b - a > 1.5 * TS_MS)
    print(f"{len(filas)} muestras, {malas} lineas danadas, {saltos} saltos de tiempo")
    return encabezado, filas


def guardar(encabezado, filas, args, n):
    os.makedirs(CARPETA, exist_ok=True)
    fecha = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    if args.modo == "trayectoria":
        ensayo = f"trayectoria_giro{args.giro}{args.tipo}"
    elif args.modo == "giro":
        ensayo = f"giro{args.giro}"
    else:
        ensayo = args.modo
    nombre = f"planta_{ensayo}_pwm{args.pwm}_{fecha}_{n}.csv"
    ruta = os.path.join(CARPETA, nombre)
    with open(ruta, "w", newline="") as f:
        f.write(encabezado + "\n")
        f.write("\n".join(filas) + "\n")
    print(f"Guardado: {ruta}")
    return ruta


def graficar(ruta):
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("Para graficar: pip install matplotlib")
        return

    with open(ruta) as f:
        columnas = f.readline().strip().split(",")
        datos = [list(map(float, l.split(","))) for l in f if l.strip()]
    col = {c: [fila[i] for fila in datos] for i, c in enumerate(columnas)}
    t = [v / 1000 for v in col["t_ms"]]

    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(15, 4.5))
    ax1.plot(t, col["pwmD"], "C0--", label="pwm D")
    ax1.plot(t, col["pwmI"], "C1--", label="pwm I")
    ax1.set_xlabel("t [s]")
    ax1.set_ylabel("PWM")
    ax1.set_title("Entrada")
    ax1.legend()
    ax1.grid(True)

    ax2.plot(t, col["wD"], "C0", label="wD")
    ax2.plot(t, col["wI"], "C1", label="wI")
    ax2.set_xlabel("t [s]")
    ax2.set_ylabel("rad/s")
    ax2.set_title("Velocidad de las ruedas")
    ax2.legend()
    ax2.grid(True)

    ax3.plot(col["x"], col["y"])
    ax3.set_xlabel("x [m]")
    ax3.set_ylabel("y [m]")
    ax3.set_title("Trayectoria (odometria)")
    ax3.axis("equal")
    ax3.grid(True)

    fig.suptitle(os.path.basename(ruta))
    fig.tight_layout()
    plt.show()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--puerto", help="ej. COM5 (por defecto se busca solo)")
    ap.add_argument("--modo", choices=list(MODOS), default="trayectoria",
                    help="trayectoria = avanzar y girar; adelante / atras = solo recto; "
                         "giro = girar en su propio eje")
    ap.add_argument("--pwm", type=int, default=120, help="0-255")
    ap.add_argument("--giro", choices=["D", "I"], default="D", help="D = derecha, I = izquierda")
    ap.add_argument("--tipo", choices=["R", "M"], default="R",
                    help="R = sobre una rueda fija, M = sobre el punto medio")
    ap.add_argument("--repeticiones", type=int, default=1)
    ap.add_argument("--graficar", action="store_true")
    args = ap.parse_args()

    puerto = args.puerto or buscar_puerto()
    print(f"Puerto: {puerto}")

    with serial.Serial(puerto, 115200, timeout=1) as ser:
        esperar_listo(ser)
        rutas = []
        for n in range(1, args.repeticiones + 1):
            if n > 1:
                input("Regresa el robot al inicio y presiona Enter...")
            print(f"--- Ensayo {n}/{args.repeticiones} ---")
            encabezado, filas = correr_ensayo(ser, args)
            rutas.append(guardar(encabezado, filas, args, n))

    if args.graficar:
        for ruta in rutas:
            graficar(ruta)


if __name__ == "__main__":
    main()
