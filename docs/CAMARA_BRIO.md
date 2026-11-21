# Cámara Logitech Brio 4K: conexión, uso y calibración

Visión del plato: la Brio mira el plato desde 20 cm, la Raspberry Pi 3 detecta la pelota y le manda su posición en mm al myRIO por UART. La laptop es opcional: sirve para **ver** la imagen y **calibrar**.

> **Estado (2026-10-29):** el código está probado en la laptop con una cámara simulada (plato negro y pelota naranja a 60 fps): detección, envío por UDP y calibración px → mm, con un error menor a 0.1 mm en la simulación. **Falta probarlo en la RPi con la Brio real.** Los tiempos de la RPi que aparecen abajo son los que se midieron el 13-oct con el detector anterior.

## 1. Cómo funciona

```text
 Brio 4K ──USB 2.0──► Raspberry Pi 3 ──UART 115200──► myRIO (control del plato)
 1280x720 MJPG        decodifica a 320x180          <x_mm,y_mm,valido,seq>
 60 fps               detecta la pelota (color)
                      px → mm
                         │
                         └──UDP (opcional)──► laptop: ver la imagen y calibrar
```

- **Todo el procesamiento va en la RPi.** El detector es liviano (umbral de color + forma): tarda unos pocos ms en 320×180.
- Procesar en la laptop por UDP es una **mejora para después** (sección 9).

| Archivo | Dónde corre | Qué hace |
| --- | --- | --- |
| `deteccion.py` | RPi y laptop | Detección de la pelota, px → mm, formato de los paquetes UDP |
| `rpi_camara.py` | RPi | Captura, detección, UART al myRIO, imagen a la laptop (opcional), medición de latencia |
| `laptop_vision.py` | Laptop | Ver la imagen, calibrar el color y calibrar px → mm |
| `config_vision.json` | Ambas | Calibración (la crea `laptop_vision.py`; se copia a la RPi) |
| `../Raspberry-Pi3B/stream_camara.py` | RPi | Video crudo de 1280×720 en el navegador, para **encuadrar y enfocar** |

## 2. Conexiones

| Qué | Conexión |
| --- | --- |
| Brio → RPi | Cable USB-C → USB-A en cualquier puerto USB de la RPi (los 4 son USB 2.0) |
| RPi → myRIO | Conector J11 de la placa 1 (ver `Electronica/plan_electronica.md`). Directo: RPi pin 8 (TX) → myRIO MXP A pin 10 (RX), RPi pin 10 (RX) ← pin 14 (TX), **RPi pin 6 (GND) ↔ DGND**. Sin el GND la UART no funciona |
| Alimentación RPi | 5 V, **≥ 2.5 A** (la RPi con la Brio consume ~2 A). Comprobar con `vcgencmd get_throttled` → `0x0` |
| Red (para SSH y la laptop) | Zona WiFi `S23+` en **2.4 GHz** (la RPi 3 no tiene 5 GHz) |

La UART ya está configurada en la microSD (`enable_uart=1` y `dtoverlay=disable-bt`). Comprobarlo con `ls -l /dev/serial0`, que debe apuntar a `ttyAMA0`.

## 3. Montaje a 20 cm

- **20 cm de la lente a la superficie del plato**, con el plato nivelado.
- La cámara **centrada sobre el pivote** del plato, con la lente paralela al plato.
- **El lado largo del plato (228 mm, eje X) a lo ancho de la imagen.** La imagen es 16:9 y el lado corto (175 mm) apenas entra a lo alto.

### Qué tanto ve la cámara a 20 cm

La Brio tiene tres campos de visión diagonales: 90°, 78° y 65°. Con el plato de 228 × 175 mm:

| Campo de visión | Ve (ancho × alto) | ¿Entra el plato? | Resolución en 320×180 |
| --- | --- | --- | --- |
| **90°** | **349 × 196 mm** | **Sí**: sobran 11 mm arriba y abajo, 60 mm a cada lado | **1.09 mm/px** |
| 78° | 282 × 159 mm | No: se cortan 8 mm arriba y abajo | 0.88 mm/px |
| 65° | 222 × 125 mm | No | 0.69 mm/px |

**Hay que usar 90°.** En la Brio, los campos de 78° y 65° son un recorte digital (zoom). `rpi_camara.py` pone `zoom_absolute=100`, el mínimo, que es el campo completo de 90°. Logi Tune había dejado el zoom en 111. Igual hay que comprobar en el video crudo (sección 6, paso 1) que se vea todo el plato.

Tamaño de la pelota en la imagen de 320×180: unos **18 px de radio con una pelota de 40 mm** (14 px con 30 mm, 23 px con 50 mm).

### Error de perspectiva (por qué se calibra con la pelota)

La cámara está muy cerca, así que lo que está más alto se ve más grande:

- **El centro de la pelota está unos 20 mm sobre el plato.** Si se calibrara con marcas en el plato vacío, cerca del borde la posición saldría ~13 mm desplazada. Por eso **la calibración se hace con la pelota misma** sobre las marcas (sección 6, paso 4): así se corrige sola.
- **Cuando el plato se inclina**, el borde sube o baja: unos 6 mm de error en el borde a 5° y unos 12 mm a 10°. En el centro el error es casi nulo. Es una limitación conocida; más adelante se puede corregir con el ángulo del IMU.

## 4. Configuración para la menor latencia

`rpi_camara.py` aplica todo esto al arrancar:

| Ajuste | Valor | Por qué |
| --- | --- | --- |
| Formato | MJPG 1280×720 a 60 fps | Por USB 2.0 es el único modo de 60 fps; los modos más chicos van a 30 fps, que suma ~17 ms entre cuadros |
| Decodificación | Reducida a **1/8 → 160×90** (`--reducir 8`, por defecto); 1/4 → 320×180 con `--reducir 4` | 6.5 ms (320×180: 9.1 ms). Las coordenadas salen siempre en la escala de 320×180, así la calibración vale para las dos |
| Búsqueda en ventana | Recuadro alrededor de la última posición; si no está, toda la imagen | 0.5 ms en vez de 0.9 ms (a 320×180: 0.9 en vez de 2.2 ms) |
| Color | **Solo el tono de la pelota** (`h_min`–`h_max`; naranja = 5–35) | Con cualquier tono pasaban los reflejos azules de la luz fría y la máscara se llenaba de fondo |
| Cuadros | `BUFFERSIZE=2` + un hilo que guarda **solo el último cuadro** | Nunca se procesa un cuadro viejo. Con `BUFFERSIZE=1` la cámara baja a 30 fps |
| Exposición | **8.3 ms** (`--exp 83`) | Es el periodo del parpadeo de las luces con la red de 60 Hz: así no aparecen bandas. Además es corta, con poca estela de movimiento |
| Framerate dinámico | Apagado | Si no, con poca luz la cámara baja los fps |
| Ganancia | `--gain 100` | Si la imagen sale oscura, **subir la ganancia**, no la exposición |
| Balance de blancos | **Manual, 4000 K** (`--wb`) | En automático el color de la pelota cambia según lo que haya en la imagen, y el umbral falla |
| Saturación | 160 (`--sat`) | Colores más fuertes, más margen para el umbral |
| Enfoque | **Manual** (`--focus`, se encuentra en el paso 1) | El autoenfoque "busca" todo el tiempo: cuadros borrosos y retardo |
| Zoom | 100 | Campo de 90° |
| UART | 115200 baud | Una trama de ~25 bytes tarda ~2 ms |

**Medido en la RPi el 31-oct** con la Brio y la pelota naranja (`bench_deteccion.py`, `rpi_camara.py --csv`):

| | 320×180 (`--reducir 4`) | **160×90 (por defecto)** |
| --- | --- | --- |
| Decodificar | 9.1 ms | **6.5 ms** |
| Detectar (en la ventana) | 0.9 ms | **0.5 ms** |
| Pelota detectada | 60/60 cuadros | 60/60 cuadros |
| Temblor con la pelota quieta | 0.05–0.10 px | 0.13–0.17 px (~0.15 mm) |
| **Latencia** (mediana / p95) | 28.9 / 33.0 ms | **25.6 / 29.6 ms** |

La latencia de 160×90 se reparte en **16.6 ms de espera** + 8.9 ms de procesamiento. La espera es justo un periodo de cuadro (60 fps): lo que tarda la Brio en pasar el cuadro por USB desde la marca de tiempo del primer paquete. Es el límite de este modo de cámara y no se baja por software. En el detector anterior (13-oct) eran 32 ms.

**Luz:** con la luz del 31-oct la pelota naranja medía V = 93 (el mínimo era 80), y la luz fría tiñe de azul todo lo que no es negro. Hace falta **más luz y más cálida sobre el plato**; mientras tanto `v_min` está en 50 (el plato negro mide V ≈ 6, así que no entra).

## 5. Instalación

**En la RPi.** OpenCV, numpy, pyserial y `v4l-utils` ya están instalados (ver `Raspberry-Pi3B/uso_rpi3.md`). Desde la laptop, en `C:\Users\User\Documents\9nvo\DSM`:

```powershell
ssh rpi-ballplate "mkdir -p ~/vision"
scp .\Project_ball\Vision\deteccion.py .\Project_ball\Vision\rpi_camara.py rpi-ballplate:~/vision/
ssh rpi-ballplate sync
```

**En la laptop.** Solo para ver y calibrar:

```powershell
pip install opencv-python numpy
```

La primera vez que corras `laptop_vision.py`, Windows preguntará si Python puede usar la red: **permitir en redes privadas**. Si no aparece la pregunta y no llega nada, revisa que el firewall deje entrar UDP al puerto **5005**.

**IP de la laptop:** en PowerShell, `ipconfig` → "Adaptador de LAN inalámbrica Wi-Fi" → `Dirección IPv4` (por ejemplo `10.192.216.50`).

## 6. Calibración (en este orden)

Hay que repetirla si se mueve la cámara, si cambia la luz (repetir el color) o si se cambia la pelota.

### Paso 1: encuadre y enfoque

Video crudo de 1280×720 en el navegador:

```powershell
scp .\Project_ball\Raspberry-Pi3B\stream_camara.py .\Project_ball\Raspberry-Pi3B\vision_ball.py rpi-ballplate:~/pruebas/
ssh -t -L 8090:localhost:8090 rpi-ballplate "cd ~/pruebas && python3 stream_camara.py --crudo --fps 5 --focus 30"
```

Abrir `http://localhost:8090`.

1. **Todo el plato debe verse**, con algo de margen arriba y abajo. Si no entra: subir la cámara, girarla (lado largo a lo ancho) o revisar el zoom.
2. **Enfoque:** probar `--focus 0, 20, 30, 40, 60` (`Ctrl+C` y volver a correr). Quedarse con el que deje los bordes del plato y de la pelota más nítidos. A 20 cm suele ser un valor medio; **anotarlo** para usarlo después en `rpi_camara.py --focus`.
3. `Ctrl+C` para cerrar: la cámara solo la puede usar un programa a la vez.

### Paso 2: luz

- Plato **negro mate**: un plato brillante refleja las lámparas. Esos reflejos son blancos y el detector los ignora, pero tapan la pelota si caen encima.
- Luz **difusa** desde arriba. Evitar una lámpara directa que deje sombra fuerte de la pelota.
- Si la pelota se ve oscura, subir `--gain` (100 → 150 → 200). No subir `--exp`: más exposición, más estela.

### Paso 3: color de la pelota

En la laptop:

```powershell
cd C:\Users\User\Documents\9nvo\DSM\Project_ball\Vision
python laptop_vision.py --calibrar-color
```

En la RPi, con la IP de la laptop:

```powershell
ssh -t rpi-ballplate "cd ~/vision && python3 rpi_camara.py --laptop 10.192.216.50 --focus 30 --ver 3"
```

Se abre una ventana con la imagen (izquierda) y la máscara (derecha). Mover las barras hasta que **en la máscara solo quede la pelota en blanco**:

| Barra | Qué hace | Punto de partida |
| --- | --- | --- |
| `s_min` | Saturación mínima. Separa la pelota del negro y de los reflejos | 110; subir si aparecen manchas del plato |
| `v_min` | Brillo mínimo | 80 |
| `h_min`, `h_max` | Tono. 0–179 = cualquier color | Naranja ≈ 5–20, verde ≈ 40–80, rojo = `h_min` 170 y `h_max` 10 |
| `r_min`, `r_max` | Radio aceptado en px | Pelota de 40 mm (r ≈ 18): 12 y 25 |

Probar la pelota en el centro, en las esquinas y con el plato inclinado. Si se usan varias pelotas de distinto color, dejar el tono en 0–179 y subir `s_min`. **`g` guarda** `config_vision.json` en la laptop; `q` sale.

### Paso 4: de px a mm en el plato

**Método usado (31-oct): por las esquinas del plato, en la RPi y sin laptop.**

Plato de **231 mm (largo, eje Y) × 175 mm (ancho, eje X)**, origen en el centro. Por defecto **+Y hacia la derecha** de la imagen y **+X hacia abajo** (hacia las piezas del robot); `--invertir-x` / `--invertir-y` los dan vuelta.

1. Plato **nivelado y quieto** (servos sosteniéndolo en 0°, sin tocarlo) y nada encima que no sea la pelota. Cables y manos lejos de los bordes.
2. Tomar una foto y leer las 4 esquinas aproximadas (bastan ±10 px), en orden arriba-izq, arriba-der, abajo-der, abajo-izq, en px de 1280×720.
3. En la RPi:

   ```bash
   cd ~/vision && python3 calibrar_esquinas.py --esquinas "325,115;967,78;975,546;350,583"
   ```

   El programa afina cada borde: desde adentro del plato busca dónde deja de ser oscuro, ajusta una recta (descartando puntos lejanos) y corta las rectas. Imprime la calidad de cada borde (**desvío mediano < 1 px**; si sale `REVISAR`, algo tapa ese borde) y deja `calib_esquinas.jpg` para revisarlo.
4. Calcula la altura de la cámara con el tamaño del plato y el campo de visión de la Brio (dio **274 mm**), y **corrige la altura de la pelota**: su centro está un radio (20 mm) sobre el plato y sin corregir habría ~8 % de error hacia los bordes. Guarda la homografía y el contorno del plato en `config_vision.json`.

Resultado del 31-oct: bordes con 0.17–0.54 px de desvío, 1.46 mm/px a 320×180. Pelota cerca del centro medida en X = +0.7, Y = −20.2 mm, que coincide con lo que se ve en la foto. **Falta verificarla con la pelota en las esquinas** (ver el paso 5).

**Método alternativo: 9 marcas con la pelota** (desde la laptop, con `laptop_vision.py`):

1. Nivelar el plato (en el ESP32 o el myRIO: ángulo 0).
2. Pegar **9 marcas** de cinta, medidas desde el centro del plato con los **mismos ejes X/Y que usa el control**: el centro, (±60, 0), (0, ±80) y (±60, ±80) mm. X va a lo ancho (175 mm) e Y a lo largo (231 mm).
3. Con `rpi_camara.py` corriendo como en el paso 3:

   ```powershell
   python laptop_vision.py --calibrar-plato --dx 60 --dy 80 --ancho 175 --alto 231
   ```

4. La ventana pide cada punto: poner la pelota sobre la marca y presionar **espacio**. Se promedian 20 detecciones.
5. Al final imprime el error en cada punto. **Debe ser menor a 2–3 mm**; si no, repetir con más cuidado en las marcas. También guarda el contorno del plato: desde entonces no se busca la pelota fuera de él.

### Paso 5: pasar la calibración a la RPi

```powershell
scp .\Project_ball\Vision\config_vision.json rpi-ballplate:~/vision/
ssh rpi-ballplate sync
```

Volver a arrancar `rpi_camara.py`. La primera línea debe decir `calibrado en mm`. Comprobar poniendo la pelota sobre las marcas: la ventana de la laptop muestra la posición en mm.

## 7. Uso normal

**Solo RPi → myRIO** (lo que se usa en el robot):

```powershell
ssh -t rpi-ballplate "cd ~/vision && python3 rpi_camara.py --uart --focus 30"
```

**Además mirando en la laptop:** primero `python laptop_vision.py` en la laptop y luego, en la RPi, el mismo comando con `--laptop <IP de la laptop>`.

Cada segundo imprime:

```text
camara  59.8 fps | resultados  59.8/s, pelota 60/60 | latencia mediana  18.2 ms, p95  21.0 ms
```

- `camara`: cuadros por segundo que entrega la Brio. Debe ser ~60.
- `pelota 60/60`: en cuántos cuadros de ese segundo encontró la pelota.
- `latencia`: desde que el cuadro llega por USB hasta que (x, y) sale por la UART. No incluye la exposición ni la compresión dentro de la cámara.

Para guardar un registro: `-t 30 --csv lat.csv` (30 s).

### Lo que recibe el myRIO

```text
<x,y,valido,seq>\n      ej. <-35.2,12.8,1,4821>\n
```

| Campo | Significado |
| --- | --- |
| `x`, `y` | Posición de la pelota en **mm desde el centro del plato**, con 1 decimal. Sin calibración (`config_vision.json` sin `homografia`) van en **px** de la imagen de 320×180 |
| `valido` | 1 = pelota encontrada. Con 0, ignorar `x` e `y` |
| `seq` | Número de cuadro. Si salta, se perdieron cuadros |

Llegan ~60 tramas/s a 115200 8N1. El VI receptor es el de `myRIO-1900/uart_rpi.md` (sección 4), con `Scan From String` y el formato `<%f,%f,%d,%d>`.

## 8. Resultados a registrar

| Prueba | fps | Pelota detectada | Latencia mediana / p95 | Error en las marcas |
| --- | --- | --- | --- | --- |
| Local (RPi), plato quieto | | | | |
| Local (RPi), pelota rodando | | | | |
| Laptop por UDP (sección 9) | | | | — |

## 9. Mejora futura: procesar en la laptop por UDP

Es la propuesta del profesor: la RPi manda la imagen a la laptop, la laptop (más potente) detecta y devuelve (x, y), y la RPi lo pasa al myRIO. El código ya lo soporta:

```powershell
# laptop
python laptop_vision.py --sin-ventana
# RPi
ssh -t rpi-ballplate "cd ~/vision && python3 rpi_camara.py --modo laptop --laptop 10.192.216.50 --uart"
```

La RPi mide la latencia **de ida y vuelta completa**, desde la captura hasta que el resultado vuelve, y la imprime igual que en el modo local. Así se comparan los dos modos con datos (tabla de la sección 8).

Antes de probarlo, conviene saber esto:

- **La RPi igual tiene que decodificar** el cuadro (11 ms) y volver a comprimirlo a 320×180 para mandarlo (~6–10 KB, ~4 Mbit/s a 60 fps). Con un detector de color, eso ya cuesta lo mismo que detectar en la RPi (3–4 ms).
- A eso se suma el **WiFi de ida y vuelta** por el hotspot del celular, que además varía (picos de decenas de ms).
- Con `--crudo` la RPi no decodifica nada y manda el JPEG de 1280×720 tal cual. Pero son 50–100 KB por cuadro, que muchas veces pasan el límite de 64 KB de un paquete UDP o del WiFi de la RPi 3. El programa cuenta y avisa los cuadros descartados.
- **Procesar en la laptop compensa cuando el modelo es pesado** (por ejemplo una red neuronal), no con un umbral de color.

## 10. Problemas comunes

| Síntoma | Causa / solución |
| --- | --- |
| `No se pudo abrir la camara` | Otro programa la tiene abierta (`stream_camara.py`, `vision_ball.py`): `pkill -f stream_camara`. O revisar `lsusb` |
| `camara` a ~30 fps | Poca luz con framerate dinámico, o alimentación débil (`vcgencmd get_throttled`) |
| El plato no entra completo | Zoom distinto de 100, cámara muy baja o girada (lado largo a lo ancho) |
| Detecta cosas fuera del plato | Falta el paso 4 (contorno del plato) o `s_min` está muy bajo |
| No detecta la pelota en una zona | Sombra o reflejo: mejorar la luz, o bajar un poco `v_min` |
| La laptop no recibe nada | IP equivocada en `--laptop`, firewall de Windows (UDP 5005), o la laptop en otra red |
| El myRIO no recibe | GND común, TX/RX cruzados, `--uart` olvidado, `/dev/serial0` debe apuntar a `ttyAMA0` |
| `sin calibrar: px` en la RPi | Falta copiar `config_vision.json` a `~/vision/` (paso 5) |

## Pendientes

- [ ] Probar en la RPi con la Brio a 20 cm y llenar la tabla de la sección 8
- [ ] Confirmar que con `zoom_absolute=100` se ve todo el plato (campo de 90°)
- [ ] Encontrar el valor de `--focus` y dejarlo como valor por defecto en `rpi_camara.py`
- [ ] Arrancar `rpi_camara.py` solo al encender la RPi (servicio de systemd)
- [ ] (Mejora) Corregir el error de perspectiva con el ángulo del plato
- [ ] (Mejora) Comparar con el modo laptop por UDP
