# Revisión del PID del plato (2026-11-02)

## Problemas del diseño `PID_asignacion_polos_Ball_and_Plate.mlx`

1. **Unidades.** `b = g/(1+2/5) = 7.007` está en m/s² por rad, así que Kp = 60.43, Ki = 167.3 y Kd = 8.277 son rad **por metro**. En LabVIEW la posición llega en **mm**: Kc = 3462 °/m equivale a **3.462 °/mm**, no 3462.
2. **Ancho de banda.** El tercer polo en p = 50 obliga a Kd grande. El lazo cruza 0 dB en ≈ b·Kd ≈ 58 rad/s, pero la cámara (60 fps) + UART + servo suman ~50–150 ms de retardo, que a esa frecuencia restan cerca de 200° de fase. **Es inestable** aun con las unidades corregidas (ver `sim_plato.py`).
3. **Sobrepaso.** Los ceros del PID dan ~10 % de sobrepaso (se ve en su propio `step`), no el < 1 % pedido.
4. **Ts < 1 s** no es alcanzable con el retardo de la cámara. Lo realista es ~1.5 s.

## Ganancias propuestas (PID.vi de NI: Kc en °/mm, Ti y Td en minutos)

| Parámetro | Valor | Equivale a |
| --- | --- | --- |
| Kc | 0.05 °/mm | Kp = 0.05·π/180 = 8.7e-4 rad/mm |
| Ti | 0 (sin integral) | El plato ya es doble integrador: el PD no deja error en régimen |
| Td | 0.0100 min | 0.6 s |
| output range | ±10 ° | Inclinación máxima del plato; evita que el integrador se cargue (antes ±100 con recorte a ±25) |

Simulación (`python sim_plato.py`, 60 Hz, ruido de 0.7 mm, saturación ±10°): asienta a ±5 mm en ~1.2 s con 50 ms de retardo y sigue estable con 150 ms. Si el plato no queda nivelado y la pelota se estaciona fuera del centro, agregar un integral suave: **Ti = 0.15 min (9 s)**.

## Ajuste en el hardware

1. Si la pelota **se aleja** del centro, el signo está invertido: usar Kc negativo (PID.vi lo admite) o invertir el eje.
2. Subir Kc de a 0.01 hasta que responda rápido sin oscilar. Si oscila rápido, bajar Td; si oscila lento, subir Td.

## Ganancias usadas en la prueba del 2-nov y recomendación

En el hardware se usó **Kc = 0.977 °/mm, Ti = 0.007 min, Td = 0.003 min** en los dos ejes. Con `sim_plato.py` (ruido 0.7 mm, saturación ±10°):

| Retardo total | Kc 0.977 / Ti 0.007 / Td 0.003 | **Kc 0.08 / Ti 0 / Td 0.008** | Kc 0.05 / Ti 0 / Td 0.010 |
| --- | --- | --- | --- |
| 50 ms | no asienta (±8 mm) | **0.9 s** | 1.2 s |
| 100 ms | **inestable** | **0.7 s** | 1.0 s |
| 150 ms | **inestable** | **2.2 s** | 1.2 s |

El retardo real es ~100–150 ms (cámara ~26 ms + servo ~100 ms + lazo). Kc = 0.977 satura el plato (±10°) con apenas 10 mm de error y Ti = 0.007 min (0.4 s) carga la integral muy rápido: el plato oscila entre los topes y la respuesta parece "lenta". **Usar Kc = 0.08, Ti = 0, Td = 0.008 min** como punto de partida; agregar Ti = 0.15 min solo si la pelota queda quieta fuera del centro.

## 3-nov: la pelota se va hacia +X (lado de la cámara) y se pierde

En `Main.vi` el servo queda en exactamente 90° cuando el PID da 0 (`+1.5708 rad` fijo): no hay forma de compensar que el plato no esté nivelado. Con un PD, un desnivel de β grados deja la pelota quieta en e = β / Kc (con Kc = 0.08 °/mm, 1° de desnivel = 12 mm; 3° = 37 mm ⇒ se va al borde). Se agregaron:

- **Offset X [°] / Offset Y [°]** (panel): se suman a la salida del PID (después del recorte ±25°), antes de convertir a ángulo de servo.
- **Registro CSV** en el myRIO: `/home/lvuser/balanceo_AAAAMMDD_HHMMSS.csv` (t_ms, x, y, ex, ey, ux, uy, valido, seq, duty_x, duty_y). `Control_balanceo_actual/bajar_registros.py` los copia a `Control_balanceo_actual/datos/` y sugiere el offset (= salida media del PID en el último tercio).

Procedimiento: (1) Kc = 0.08, Ti = 0, Td = 0.008; correr ~20 s; (2) `python bajar_registros.py`; (3) poner Offset = valor sugerido; (4) recién después agregar Ti = 0.15 min para el error que quede.

### Primera corrida registrada (3-nov, `Control_balanceo_actual/datos/balanceo_19700101_000105.csv`)

Ganancias estimadas de los datos: X Kc 0.080, Td 0.013 min; **Y Kc 0.080, Td 0.13 min (10× X: el eje Y quedó saturado ±25° el 53 % del tiempo, bang-bang)**. Output range ±25°. Signo correcto en ambos ejes. Planta medida: X ≈ 60 mm/s² por grado con ~84 ms de retardo; Y no se puede medir bien mientras esté saturado. Desnivel: X ≈ −2.5° (por eso deriva a +X y se cae en x ≈ 80 mm), Y ≈ +0.6°. Siguiente prueba: Td Y = 0.008, output range ±10, Offset X = −2.5, Offset Y = 0.

### Segunda corrida (3-nov, `balanceo_19700101_001127.csv`, Kc ≈ 0.07, Td ≈ 0.007 min, ±10°)

Ya no satura (1 %). La pelota queda quieta ~100 s en (x, y) ≈ (+38, +68) mm con el PID dando −3.0° y −5.3°: es exactamente e = desnivel / Kc, o sea el plato está desnivelado ~3° en X y ~5° en Y respecto de lo que había en los Offset. Corrección: sumar −3.0 al Offset X y −5.3 al Offset Y (o recentrar los brazos de los servos), y después Ti ≈ 0.1–0.15 min.
