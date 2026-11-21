# UART Raspberry Pi → myRIO-1900

Enlace serie por el que la RPi envía la posición de la pelota detectada por la cámara.

## 1. Cableado

Las dos placas usan lógica de 3.3 V, así que se conectan **directo**, sin divisor ni conversor de nivel. TX y RX se **cruzan**.

| Raspberry Pi 3B (header de 40 pines) | | myRIO MXP A |
| --- | --- | --- |
| Pin 8 — GPIO14 (TXD) | → | Pin 10 — UART.RX |
| Pin 10 — GPIO15 (RXD) | ← | Pin 14 — UART.TX |
| Pin 6 — GND | — | Pin 12 — DGND |

> Conectar siempre el GND. Sin GND común no llega nada o llega basura.

## 2. Parámetros

| Parámetro | Valor |
| --- | --- |
| Baud rate | 115200 (el myRIO admite hasta 230400) |
| Formato | 8N1, sin control de flujo |
| Terminador | `\n` (0x0A) |
| Trama RPi → myRIO | `<x,y,valid,seq>\n` — ej. `<160.2,90.5,1,1234>\n` |
| Recurso VISA | MXP A = `ASRL1::INSTR`, MXP B = `ASRL2::INSTR` (verificar en el desplegable de VISA resource del target) |

| Campo | Tipo | Significado |
| --- | --- | --- |
| `x`, `y` | float, 1 decimal | Centro de la pelota en **mm desde el centro del plato** (`Vision/rpi_camara.py` con la cámara calibrada). Sin calibrar, en píxeles de la imagen de 320×180 (origen arriba a la izquierda) |
| `valid` | 0/1 | 1 = pelota detectada en ese cuadro |
| `seq` | entero | Número de cuadro. Si salta, se perdió una trama |

A 115200 baud, una trama de ~21 bytes tarda **~1.8 ms** en el cable. A 60 tramas/s se usa ~11% del canal.

## 3. VI 1 — Eco (prueba de ida y vuelta)

Devuelve cada línea tal como la recibe. Así la RPi mide el tiempo de ida y vuelta (RTT) con `uart_test.py rtt`.

```text
VISA Configure Serial Port
    VISA resource  = ASRL1::INSTR
    baud rate      = 115200, data bits 8, parity None, stop bits 1, flow control None
    enable termination char = TRUE, termination char = 10 (\n)
    timeout        = 100 ms
        │
While Loop (sin Wait: VISA Read ya espera)
    VISA Read (byte count = 64)          -> termina al recibir \n
    si return count > 0  -> VISA Write (mismo string)
    si error = timeout (-1073807339)  -> limpiar error y seguir
    Stop: botón STOP o error distinto de timeout
        │
VISA Close
```

## 4. VI 2 — Receptor de posición

```text
VISA Configure Serial Port (igual que arriba)
        │
While Loop exterior
    While Loop interior  ── vacia el buffer y se queda con la ULTIMA linea
        VISA Read (byte count = 64)        -> una linea por lectura (termina en \n)
        Property Node VISA: Bytes at Port  -> stop si = 0
        tunel de salida "Last Value"       -> ultima linea completa
        i + 1                              -> lineas leidas en esta vuelta
    Scan From String  formato: %.;<%f,%f,%d,%d>   -> x, y, valid, seq
                      (%.; = punto decimal siempre, aunque Windows este en espanol)
    perdidas += (seq - seq_anterior - lineas_leidas)
    cada 1 s (Tick Count): tramas/s = contador; contador = 0
    Indicadores: x, y, valid, seq, tramas/s, perdidas
    Waveform Chart: x, y
        │
VISA Close
```

**Recomendaciones:**

- **Errores que no deben detener el lazo:** además del timeout (−1073807339), limpiar el **framing** (−1073807253) y el **overrun** (−1073807252) con un `Clear Errors` cada uno, en serie después de `VISA Read`. El framing aparece al abrir el puerto en medio de una trama (la RPi ya está transmitiendo) o con un byte con ruido; la línea dañada no pasa el `Scan From String` y se cuenta como pérdida. Sin esto, el VI se detiene al primer byte malo (visto el 30-oct).
- No pongas `Wait` dentro del lazo de lectura. Si el lazo lee más lento de lo que llegan las tramas (60/s), se acumulan en el buffer y la posición que procesas queda **atrasada**.
- Si solo te interesa la posición más reciente, lee todo lo disponible (`Bytes at Port`) y quédate con la **última línea completa**.
- Corre este lazo separado del lazo de control. Pasa la posición al control con una variable local, un notificador o una variable compartida de un solo elemento.

## 5. Pruebas desde la RPi

```bash
cd ~/pruebas
python3 uart_test.py rtt -n 500              # RTT con el VI de eco (o loopback pin 8 <-> pin 10)
python3 uart_test.py stream -r 60 -t 10      # 60 tramas/s simuladas -> ver tramas/s en el VI 2
python3 vision_ball.py --uart -t 30          # posiciones reales de la cámara
```
