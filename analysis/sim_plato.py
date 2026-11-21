"""Simula un eje del ball-plate: x'' = b*sin(theta), PID.vi de NI (Kc deg/mm, Ti/Td en min, derivada sobre PV),
muestreo 60 Hz (camara), retardo total tau, salida saturada a +-sat grados."""
import math, sys
b = 9.81e3 / (1 + 2 / 5)          # mm/s^2 por rad
def sim(Kc, Ti_min, Td_min, tau=0.08, sat=10.0, x0=80.0, T=8.0, ruido=0.0):
    import random; random.seed(1)
    dt = 1 / 600; Ts = 1 / 60; n_d = round(tau / Ts)
    x, v, I, pv_prev = x0, 0.0, 0.0, x0
    cola = [0.0] * (n_d + 1); th = 0.0; t = 0.0; k = 0; xs = []
    Ti, Td = Ti_min * 60, Td_min * 60
    while t < T:
        if k % 10 == 0:                               # muestra de la camara
            pv = x + random.gauss(0, ruido)
            e = 0.0 - pv
            I = I + (Kc / Ti * e * Ts if Ti > 0 else 0)
            I = max(-sat, min(sat, I))                # antiwindup por recorte
            u = Kc * e + I - Kc * Td * (pv - pv_prev) / Ts
            pv_prev = pv
            u = max(-sat, min(sat, u))
            cola.append(u); th = cola.pop(0)
        v += b * math.sin(math.radians(th)) * dt; x += v * dt; t += dt; k += 1
        xs.append((t, x))
        if abs(x) > 300: return None
    pico = max(abs(p) for _, p in xs if _ > 0.2)
    ts = next((tt for tt, _ in reversed(xs) if abs(_) > 0.02 * x0 * 2.5), 0)
    final = max(abs(p) for tt, p in xs if tt > T - 2)
    return ts, final
def show(nombre, *a, **kw):
    r = sim(*a, **kw)
    print(f"{nombre:38s}", "INESTABLE / se cae del plato" if r is None or r[1] > 30 else f"asienta (+-5 mm) en {r[0]:.2f} s, residuo {r[1]:.1f} mm")
for tau in (0.05, 0.08, 0.12):
    print(f"-- retardo total {tau*1000:.0f} ms")
    show("Amiga (unidades corregidas) Kc=3.46", 3.462, 0.0060, 0.0023, tau=tau)
    show("Propuesto Kc=0.023 Ti=0.083 Td=0.0133", 0.023, 0.0833, 0.0133, tau=tau)
    show("Propuesto + ruido camara 0.7 mm", 0.023, 0.0833, 0.0133, tau=tau, ruido=0.7)
