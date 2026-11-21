"""Pruebas de la UART RPi -> myRIO.

Trama (ASCII, 8N1, terminador \\n):   <x,y,valid,seq>\\n     ej. <160.2,90.5,1,1234>\\n

Modos:
  rtt     Envia tramas y espera que vuelvan (eco). Mide el tiempo de ida y vuelta.
          - Sin myRIO: puentear GPIO14 (pin 8) con GPIO15 (pin 10) -> "loopback".
          - Con myRIO: el VI del myRIO debe devolver cada linea tal cual la recibe.
  stream  Envia tramas de posicion (simuladas) a una frecuencia fija, sin esperar respuesta.
          Si el myRIO responde, cuenta las respuestas.

Uso:
  python3 uart_test.py rtt -n 500
  python3 uart_test.py rtt -b 230400
  python3 uart_test.py stream -r 60 -t 10
  python3 uart_test.py stream -r 0 -t 5      # tan rapido como se pueda
"""
import argparse
import math
import statistics as st
import time

import serial

PUERTO = "/dev/serial0"


def trama(x, y, valid, seq):
    return f"<{x:.1f},{y:.1f},{int(valid)},{seq}>\n".encode()


def pos_simulada(t):
    """Pelota simulada recorriendo un circulo en la imagen de 320x180."""
    return 160 + 60 * math.cos(2 * math.pi * 0.5 * t), 90 + 40 * math.sin(2 * math.pi * 0.5 * t)


def percentil(v, p):
    v = sorted(v)
    return v[min(len(v) - 1, int(p / 100 * len(v)))]


def modo_rtt(ser, n, timeout):
    ser.timeout = timeout
    rtts, perdidas, corruptas = [], 0, 0
    ser.reset_input_buffer()
    for seq in range(n):
        x, y = pos_simulada(seq / 60)
        tx = trama(x, y, 1, seq)
        t0 = time.perf_counter()
        ser.write(tx)
        rx = ser.read_until(b"\n")
        dt = time.perf_counter() - t0
        if not rx:
            perdidas += 1
        elif rx != tx:
            corruptas += 1
            ser.reset_input_buffer()
        else:
            rtts.append(dt * 1000)
    print(f"tramas {n} | ok {len(rtts)} | perdidas {perdidas} | corruptas {corruptas}")
    if rtts:
        print(f"RTT ms: min {min(rtts):.2f} | mediana {st.median(rtts):.2f} | "
              f"p95 {percentil(rtts, 95):.2f} | max {max(rtts):.2f}")
        bits = 10 * len(tx)  # 8N1 = 10 bits por byte
        print(f"tiempo teorico en el cable por trama ({len(tx)} B): {1000 * bits / ser.baudrate:.2f} ms "
              f"(ida) / {2000 * bits / ser.baudrate:.2f} ms (ida y vuelta)")


def modo_stream(ser, rate, dur):
    ser.timeout = 0
    periodo = 1 / rate if rate > 0 else 0
    n = nbytes = resp = 0
    t_write = []
    buf = b""
    t0 = t_next = time.perf_counter()
    while time.perf_counter() - t0 < dur:
        if periodo:
            espera = t_next - time.perf_counter()
            if espera > 0:
                time.sleep(espera)
            t_next += periodo
        t = time.perf_counter()
        x, y = pos_simulada(t - t0)
        tx = trama(x, y, 1, n)
        t1 = time.perf_counter()
        ser.write(tx)
        t_write.append((time.perf_counter() - t1) * 1000)
        n += 1
        nbytes += len(tx)
        buf += ser.read(ser.in_waiting or 0)
        resp += buf.count(b"\n")
        buf = buf[buf.rfind(b"\n") + 1:]
    ser.flush()
    dt = time.perf_counter() - t0
    print(f"tramas {n} en {dt:.2f} s -> {n / dt:.1f} tramas/s | {nbytes / dt:.0f} B/s "
          f"({100 * 10 * nbytes / dt / ser.baudrate:.0f}% del canal a {ser.baudrate})")
    print(f"write() ms: mediana {st.median(t_write):.3f} | p95 {percentil(t_write, 95):.3f} | "
          f"max {max(t_write):.3f}")
    print(f"respuestas recibidas: {resp}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("modo", choices=["rtt", "stream"])
    ap.add_argument("-b", "--baud", type=int, default=115200)
    ap.add_argument("-p", "--puerto", default=PUERTO)
    ap.add_argument("-n", type=int, default=300, help="tramas (modo rtt)")
    ap.add_argument("-r", "--rate", type=float, default=60, help="tramas/s, 0 = maximo (modo stream)")
    ap.add_argument("-t", "--tiempo", type=float, default=10, help="segundos (modo stream)")
    ap.add_argument("--timeout", type=float, default=0.2, help="espera por eco [s] (modo rtt)")
    a = ap.parse_args()

    with serial.Serial(a.puerto, a.baud, bytesize=8, parity="N", stopbits=1) as ser:
        print(f"{a.puerto} @ {a.baud} 8N1")
        if a.modo == "rtt":
            modo_rtt(ser, a.n, a.timeout)
        else:
            modo_stream(ser, a.rate, a.tiempo)


if __name__ == "__main__":
    main()
