"""Captura los experimentos del plato (PlantaBall.ino en el ESP32) y los guarda en CSV.

Antes, desde el Monitor Serie: nivelar (N), revisar y guardar (G). Ver PlantaBall.ino.
Despues cerrar el Monitor Serie: el puerto solo lo puede usar un programa a la vez.

Experimentos:
  escalones  0, +1, 0, -1, 0, +2, 0, -2, 0 veces --amp, 1.5 s cada tramo (13.5 s)
  seno       0.5 s quieto, 10 s de seno de --amp grados, 0.5 s quieto

Con --lazo-cerrado la referencia entra al PI del ESP32 (comandos R / S) en
lugar de ir directo al plato. Las ganancias se cargan antes con K,eje,kp,ki,kd.

Uso:
  python capturar_plato.py --eje X --amp 2                       # escalones en X
  python capturar_plato.py --eje A --amp 3 --graficar            # escalones en ambos ejes
  python capturar_plato.py --seno --eje Y --amp 2 --freq 0.5 1 2 4
  python capturar_plato.py --eje X --amp 2 --repeticiones 3
  python capturar_plato.py --lazo-cerrado --eje X --amp 2 --graficar
"""
import argparse
import datetime
import os
import sys
import time

import serial

from capturar_planta import buscar_puerto, leer_linea

CARPETA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "datos_plato")
DURACION_S = {"escalones": 13.5, "seno": 11.0}


def abrir(puerto):
    ser = serial.Serial()
    ser.port = puerto
    ser.baudrate = 115200
    ser.timeout = 1
    # En el ESP32, DTR/RTS reinician la placa: dejarlos apagados para no
    # perder la nivelacion ni el sesgo del giroscopio.
    ser.dtr = False
    ser.rts = False
    ser.open()
    time.sleep(0.2)
    ser.reset_input_buffer()
    return ser


def correr(ser, comando, duracion_s):
    """Envia el comando y devuelve (encabezado, filas) del CSV que vuelca el ESP32."""
    ser.reset_input_buffer()
    ser.write((comando + "\n").encode())
    print(f"Enviado: {comando}  (~{duracion_s:.0f} s de ensayo + volcado)")

    encabezado = None
    filas = []
    malas = 0
    # Durante el ensayo el ESP32 no manda nada; despues, mientras lleguen
    # lineas se sigue esperando.
    ultima = time.time()

    while time.time() - ultima < duracion_s + 30:
        linea = leer_linea(ser)
        if not linea:
            continue
        ultima = time.time()
        if linea.startswith("#"):
            print(linea)
            if linea.startswith("# FIN"):
                break
            continue
        if encabezado is None:
            if linea.startswith("t_ms"):
                encabezado = linea
            continue
        if linea.count(",") == encabezado.count(","):
            filas.append(linea)
        else:
            malas += 1
    else:
        sys.exit("No llego '# FIN'. Revisa el puerto y que el ESP32 tenga PlantaBall.ino.")

    if encabezado is None:
        sys.exit("No llegaron datos.")
    print(f"{len(filas)} muestras, {malas} lineas danadas")
    return encabezado, filas


def guardar(encabezado, filas, nombre):
    os.makedirs(CARPETA, exist_ok=True)
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

    # Sin potenciometros las columnas th*_pot vienen en nan: no graficar esa fila.
    hay_pot = any(v == v for v in col["thx_pot"] + col["thy_pot"])
    filas = 2 if hay_pot else 1
    fig, ejes = plt.subplots(filas, 2, figsize=(13, 3.5 * filas + 0.5), sharex=True, squeeze=False)
    for j, e in enumerate("xy"):
        ax = ejes[0][j]
        lazo_cerrado = f"a{e}_ref" in col and col[f"a{e}_ref"] != col[f"a{e}_cmd"]
        if lazo_cerrado:
            ax.plot(t, col[f"a{e}_ref"], "k--", label="alpha referencia")
            ax.plot(t, col[f"a{e}_cmd"], "C2", lw=0.8, label="alpha_cmd (salida del PI)")
        else:
            ax.plot(t, col[f"a{e}_cmd"], "k--", label="alpha pedido")
        ax.plot(t, col[f"a{e}_imu"], "C0", label="alpha IMU")
        ax.set_xlabel("t [s]")
        ax.set_ylabel("grados")
        ax.set_title(f"Plato eje {e.upper()}")
        ax.legend()
        ax.grid(True)

        if not hay_pot:
            continue
        ax = ejes[1][j]
        ax.plot(t, col[f"th{e}_cmd"], "k--", label="theta servo pedido")
        ax.plot(t, col[f"th{e}_pot"], "C1", label="theta potenciometro")
        ax.set_xlabel("t [s]")
        ax.set_ylabel("grados")
        ax.set_title(f"Servo eje {e.upper()}")
        ax.legend()
        ax.grid(True)

    fig.suptitle(os.path.basename(ruta))
    fig.tight_layout()
    plt.show()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--puerto", help="ej. COM7 (por defecto se busca solo)")
    ap.add_argument("--seno", action="store_true", help="seno en lugar de escalones")
    ap.add_argument("--eje", choices=["X", "Y", "A"], default="X", help="A = ambos ejes a la vez")
    ap.add_argument("--amp", type=float, default=2.0, help="amplitud en grados del plato")
    ap.add_argument("--freq", type=float, nargs="+", default=[1.0],
                    help="frecuencias del seno en Hz (se hace un ensayo por cada una)")
    ap.add_argument("--repeticiones", type=int, default=1)
    ap.add_argument("--lazo-cerrado", action="store_true",
                    help="la referencia entra al PI del ESP32 (comandos R / S)")
    ap.add_argument("--graficar", action="store_true")
    args = ap.parse_args()

    tipo = "seno" if args.seno else "escalones"
    frecuencias = args.freq if args.seno else [None]
    prefijo = "plato_lc" if args.lazo_cerrado else "plato"
    cmd_esc, cmd_seno = ("R", "S") if args.lazo_cerrado else ("E", "W")

    puerto = args.puerto or buscar_puerto()
    print(f"Puerto: {puerto}")

    rutas = []
    with abrir(puerto) as ser:
        for freq in frecuencias:
            for n in range(1, args.repeticiones + 1):
                fecha = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                if args.seno:
                    comando = f"{cmd_seno},{args.eje},{args.amp},{freq}"
                    nombre = f"{prefijo}_seno_{args.eje}_amp{args.amp:g}_f{freq:g}_{fecha}_{n}.csv"
                else:
                    comando = f"{cmd_esc},{args.eje},{args.amp}"
                    nombre = f"{prefijo}_escalones_{args.eje}_amp{args.amp:g}_{fecha}_{n}.csv"
                encabezado, filas = correr(ser, comando, DURACION_S[tipo])
                rutas.append(guardar(encabezado, filas, nombre))

    if args.graficar:
        for ruta in rutas:
            graficar(ruta)


if __name__ == "__main__":
    main()
