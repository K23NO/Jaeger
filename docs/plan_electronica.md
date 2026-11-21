# Plan de electrónica — Robot móvil ball-and-plate

Electrónica completa del robot: panel táctil, PCB principal, adaptador del panel, distribución de energía y cableado al myRIO. Revisión del 2026-10-25.

**Plazos:** diseño de pistas entregado a la CNC el **mié 28-oct**; todo soldado y probado el **jue 29-oct**. El control (PID, LQI, fuzzy, SMC, Kalman) empieza después y no forma parte de este documento.

---

## 0. Decisiones y por qué

| Decisión | Por qué |
| --- | --- |
| **Todo el control en el myRIO-1900; la RPi 3 Model B v1.2 solo hace visión** (posición de la pelota con la Brio, por UART). | El myRIO tiene las entradas y salidas de sobra (tabla de la sección 3). Un micro extra agregaría un enlace con retardo y otro programa. |
| **El ESP32 no va en el robot.** Se usa solo en el banco, para probar el panel antes de pasarlo a LabVIEW. | — |
| **La posición de la pelota se mide con el panel y con la cámara.** | Después se comparan los dos y se combinan con un Kalman. La electrónica solo tiene que dejar las dos mediciones disponibles. |
| **Panel resistivo leído con un 74HC4066 + 2 AI + 2 DIO del myRIO.** | Se arma con piezas de Lima. Un controlador dedicado (XPT2046) solo se consigue en SMD o soldado en módulos TFT. |
| **La IMU (MPU-6050, módulo GY-521) va en el plato**, no en la base. | Mide el ángulo absoluto del plato para el lazo interno de ángulo. Con eso se compensa sola la pendiente (hasta ~20°) de la base. |
| **No se cablea el potenciómetro de los servos.** | En los 6 ensayos de escalones (`Pruebas_Arduino/datos_plato`), potenciómetro/comando da 0.98–1.01: el servo llega a donde se le pide. Lo que se pierde (IMU/comando ≈ 0.8) está en la biela y las holguras, y eso solo lo ve la IMU. El potenciómetro tiene el mismo retardo (~100 ms) y unas 50 veces más ruido. **Se deja el cable soldado pero sin conectar**, por si hace falta diagnosticar un servo trabado en la pendiente. |
| **Dos placas:** la **PCB principal** al frente del chasis y la **placa 2 (adaptador + conversor del panel)** en el borde del plato. La placa 2 lleva el conector a presión, el 74HC4066 y los filtros, y sale un cable de 6 hilos. Todo lo demás va por cables. | Debajo del plato está el soporte de 2 ejes y no cabe una placa grande. Con el conversor en la placa 2, esa placa se puede probar sola con el ESP32 antes de que exista la PCB principal. |
| **Potencia sin caja de fusibles:** interruptor → borneras de distribución, con **fusibles en línea** en las ramas de cable delgado. | Es lo más simple que sigue protegiendo los cables delgados. El fusible de 20 A de la batería solo protege el tramo grueso. |

---

## 1. Restricciones de fabricación (CNC de la universidad)

| Regla | Valor | Qué implica |
| --- | --- | --- |
| Capas | **1, la inferior (bottom)** | Componentes THT arriba y cobre abajo. **No hay vías**: los cruces se resuelven con **puentes de alambre** por arriba (máximo ~5). |
| Vías metalizadas | No | Ídem. |
| Tamaño máximo | 10 × 10 cm | La PCB principal se diseña para **≤ 95 × 95 mm**. |
| Ancho de pista mínimo | 0.6 mm | Se usa **0.8–1.0 mm** en las señales, con margen por si la fresa se come cobre. |
| Separación pista–pista | 0.8 mm | Paso mínimo entre pistas paralelas: 1.4 mm. |
| Clearance mínimo | 0.3 mm | Se interpreta como la distancia de un pad a otro cobre. **Confirmar en el laboratorio** si los pads pueden quedar a 0.3–0.4 mm (solo importa para el adaptador del panel, sección 4). |

Consecuencias directas:

- **Entre dos pines de 2.54 mm no pasa ninguna pista**: la separación entre pads (~0.9 mm) es menor que 0.6 + 2 × 0.3 mm. Esto vale para los conectores 2×17 de tipo caja y para el DIP-14. Cada fila sale hacia su lado (sección 5.4).
- **El cobre que la CNC no quita se deja como plano de tierra.** Todas las islas de cobre se unen a GND.
- **Ojo con el espejado:** el cobre está abajo, así que el pin 1 de los conectores se verifica **mirando la placa desde arriba**. Antes de mandar a fresar, imprime el diseño en papel a escala 1:1 y pincha los componentes reales.

---

## 2. Arquitectura

```text
                         PLATO (se mueve)                         │         CHASIS (fijo)
                                                                  │
 Panel 4 hilos ─ cable plano ─ [PLACA 2: ADAPTADOR ═ 6 hilos ═════╪══► J3 ┐
                                 + 74HC4066] (borde del plato)    │       │
 MPU-6050 (al plato, junto al pivote) 4 hilos (I2C, trenzado) ═════╪══► J4 │
 Servo X / Servo Y (cable original de 3 hilos) ═══════════════════╪══► J8/J9   PCB PRINCIPAL ── J1 ═ jumpers Dupont ═ MXP A ┐
                                                                  │       │    (≤ 95×95 mm)  ── J2 ═ jumpers Dupont ═ MXP B ┤ myRIO-1900
                                          Encoders 1 y 2 ═════════╪══► J5/J6                                                │
                                          Cytron MDD10A ══════════╪══► J7                                                   │
                                          RPi 3B (UART) ══════════╪══► J11                                                  │
                                          Buck 5–6 V servos ══════╪══► J10 (bornera)                                        │
                                                                  │                                                         │
 Batería 12 V ─ interruptor ─ borneras de distribución ─ fusibles en línea ─┬─ myRIO (con Schottky + 1000 µF) ───────────────┘
                                                                            ├─ Cytron MDD10A ─ motores
                                                                            └─ Buck 5–6 V ─ J10 (servos)

 RPi 3B (+ Brio por USB) ─ batería portátil USB aparte, por micro-USB. GND común con el myRIO solo por el hilo GND del UART (J11).
```

Los cables que cruzan la articulación del plato (adaptador del panel, IMU y servos) se dejan con **holgura para ±30°** en los dos ejes. Se sujetan con cintillos al soporte, cerca del eje de giro, para que no se tensen.

---

## 3. Asignación de pines del myRIO (fuente única; reemplaza la tabla del README)

Pinout MXP del myRIO-1900: fila impar = 1, 3, …, 33; fila par = 2, 4, …, 34.

### MXP A → J1 (tira hembra 1×20)

> [!NOTE]
> **Actualización de pines de Servos (31-oct-2026):**
> * **Servo Y:** Conectado a **MXP A, Pin 31 (A/PWM2)**.
> * **Servo X:** Conectado a **MXP B, Pin 31 (B/PWM2)**.
> Ambos usan el canal de hardware `PWM2` de cada conector MXP (50 Hz, periodo 20 ms).

Reasignación para rutear la placa y conectar actuadores: "Pos." es la posición en la tira J1, contada desde el pad 1 (cuadrado).

| Pos. J1 | Pin | Señal myRIO | Va a | Conector PCB / Dispositivo |
| --- | --- | --- | --- | --- |
| 1 | 10 | UART.RX | RPi TX (GPIO14, pin físico 8) | J11.1 |
| 2 | 14 | UART.TX | RPi RX (GPIO15, pin físico 10) | J11.2 |
| 3 | 8 | DGND | Compuerta del plano de GND | — |
| 4 | 1 | +5V | VCC encoder motor 1 | J5.1 |
| 5 | 18 | ENC.A | Encoder motor 1, canal A | J5.2 |
| 6 | 12 | DGND | Compuerta del plano de GND | — |
| 7 | 22 | ENC.B | Encoder motor 1, canal B | J5.4 |
| 8 | 19 | DIO4 | Cytron DIR1 | J7.1 |
| 9 | 27 | PWM0 | Cytron PWM1 (R5 de 4.7 kΩ a GND) | J7.2 |
| 10 | 16 | DGND | Compuerta del plano de GND | — |
| 11 | 21 | **DIO5** | **Cytron DIR2** | J7.3 |
| 12 | 29 | **PWM1** | **Cytron PWM2** (R6 de 4.7 kΩ a GND) | J7.4 |
| — | **31** | **PWM2** | **Señal servo Y** | **Pin 31 MXP A** |
| 13 | 20 | DGND | Compuerta del plano de GND | — |
| 14 | 7 | AI2 | Voltaje de la batería (VBAT × 0.236, divisor R11/R12 + C14) | J12 |
| 15 | 5 | AI1 | Lectura Y del panel (desde X+) | J3.1 |
| 16 | 6 | AGND | GND del circuito del panel (unido a GND solo en NT2) | J3.2 |
| 17 | 11 | DIO0 | MEDIR_X → 74HC4066 de la placa 2 | J3.3 |
| 18 | 33 | +3.3V | VCC del 74HC4066 y excitación del panel | J3.4 |
| 19 | 13 | DIO1 | MEDIR_Y → 74HC4066 de la placa 2 | J3.5 |
| 20 | 3 | AI0 | Lectura X del panel (desde Y+) | J3.6 |

### MXP B → J2 (tira hembra 1×11)

| Pos. J2 | Pin | Señal myRIO | Va a | Conector PCB / Dispositivo |
| --- | --- | --- | --- | --- |
| — | **31** | **PWM2** | **Señal servo X** | **Pin 31 MXP B** |
| 2 | 8 | DGND | Compuerta del plano de GND | — |
| 4 | 1 | +5V | VCC encoder motor 2 | J6.1 |
| 5 | 18 | ENC.A | Encoder motor 2, canal A | J6.2 |
| 6 | 12 | DGND | Compuerta del plano de GND | — |
| 7 | 22 | ENC.B | Encoder motor 2, canal B | J6.4 |
| 8 | 33 | +3.3V | MPU-6050 VCC (entrada del regulador del GY-521) | J4.1 |
| 9 | 16 | DGND | Compuerta del plano de GND | — |
| 10 | 32 | I2C.SCL | MPU-6050 SCL | J4.3 |
| 11 | 34 | I2C.SDA | MPU-6050 SDA | J4.4 |

**Las posiciones de DGND son "compuertas":** el pad deja pasar el plano de GND entre pistas vecinas. Electricamente basta con que el GND llegue por un jumper, pero conviene cablear **al menos 2 DGND por MXP** (por ejemplo A8 y A12, B8 y B12).

Ya se verificó que los encoders se leen bien en ENC.A/ENC.B de los dos MXP. Los encoders usan 5 V y las DIO del myRIO aceptan 5 V en la entrada.

**Datos del manual de NI** ([NI myRIO-1900 User Guide and Specifications](https://download.ni.com/support/manuals/376047c.pdf), revisado el 27-oct-2026):

| Punto | Dato | Qué implica |
| --- | --- | --- |
| Conector MXP | **Macho con caja** (box header 2×17, 2.54 mm, DIN 41651) y con muesca, en el borde superior. Pin 1 de B a 19.4 mm y pin 1 de A a 76.6 mm de la esquina (57.2 mm entre los dos), a 15.4 mm de altura (fig. 13). | Entra un IDC hembra de cable plano o jumpers Dupont hembra sueltos. **Se eligieron jumpers Dupont** (27-oct): en Lima no se encontraron box headers ni IDC de 34. En la PCB van **tiras hembra de 1 fila** con solo los pines usados, en el orden de ruteo (sección 3). |
| Pinout | Fig. 3 del manual | Coincide pin por pin con las tablas de arriba. Los DGND son 8, 12, 16, 20, 24, 28 y 30. |
| DIO 0–13, UART | Pull-up interno de 40 kΩ a 3.3 V; flotan en alto al arrancar | Confirma la causa de la sección 7.3. Con 4.7 kΩ a GND la línea queda en 0.35 V (VIL máx. 0.8 V). |
| DIO 14/15 (I2C) | **Pull-up interno de 2.1 kΩ** a 3.3 V | No hacen falta pull-ups en la PCB (R7/R8 se quitaron). |
| Entradas DIO | VIH 2.0–5.25 V | Aceptan los encoders de 5 V. |
| +5 V / +3.3 V | 100 mA / 150 mA **por conector** | Un encoder por conector (+5 V); panel en A e IMU en B (+3.3 V). |
| UART | Hasta 230 400 baud | — |
| Cables de señal | Máximo 30 cm (prueba de EMC) | **Jumpers de ≤ 30 cm** (los de 20 cm comunes sirven). |

**UART de la RPi 3B:** el UART principal de los GPIO 14/15 viene asignado al Bluetooth. Hay que agregar `dtoverlay=disable-bt` en `/boot/config.txt` y desactivar la consola serie (`raspi-config` → Interface → Serial: consola **no**, hardware **sí**). Los dos lados usan 3.3 V, así que se conectan directo.

**Consumo del +3.3 V del myRIO** (máximo 150 mA): 74HC4066 + panel (~7 mA) en MXP A, MPU-6050 (~4 mA) en MXP B. Sobra.

---

## 4. Placa 2 — Adaptador + conversor del panel (borde del plato)

Proyecto KiCad: `Electronica/Placa2/`. Avance y notas de trabajo en `Electronica/Placa2/CLAUDE.md`.

### 4.0 Contenido (diseño final, 26-oct-2026)

| Ref. | Qué | Notas |
| --- | --- | --- |
| J21 | **Contacto a presión del cable del panel** (`Placa2:Panel_FPC_4P_P1.0mm_Presion`) | 4 pads de **0.6 mm con paso de 1.0 mm** en **B.Cu**: el cable se aprieta contra el cobre, por debajo de la placa. Zona de contacto de 4 mm. Los pads 1 y 3 se alargan 2 mm hacia el 4066 y los pads 2 y 4 se alargan 2 mm hacia el borde, por debajo del cuerpo del cable, para que las pistas puedan salir. El pad 1 es cuadrado. Orden: **1 = Y+, 2 = X+, 3 = Y−, 4 = X−** (sección 4.2). |
| H21, H22 | 2 agujeros M3 para la abrazadera de los contactos | A los lados de J21, en y = −46.5. |
| H23, H24 | 2 agujeros M3 para apretar el cuerpo del cable | En y = −53.5, más cerca del borde. |
| H25, H26 | 2 agujeros M3 para fijar la placa al plato | — |
| U21 | 74HC4066 en zócalo DIP-14 (through-hole), con C23 de 100 nF | Circuito de la sección 5.2, con la asignación de pines de la sección 4.1. |
| R21, R22 | 1 kΩ 1 % | Filtros RC de las lecturas. |
| C21, C22 | **1 nF C0G o X7R** (código 102) | Con pelota: τ = (1 kΩ + ~5 kΩ de contacto) × 1 nF ≈ 6 µs. Sin pelota, el nodo viene cargado a ~3.3 V del eje anterior y se descarga solo por R23/R24: τ ≈ 0.15 ms, baja a 0.2 V en 0.43 ms. Con 10 nF o 100 nF tardaría varios ms y el software leería una pelota que no está. |
| R23, R24 | **220 kΩ 1 %** | Pull-downs (detectan "sin pelota"). En paralelo con la entrada del myRIO (~500 kΩ) cargan la lectura un 3.5 % con 5 kΩ de contacto; la calibración absorbe la parte que depende de la posición. Fuga máxima del 4066 apagado (0.1 µA) × 220 kΩ = 22 mV, despreciable frente a la lectura mínima válida (0.42 V). |
| — | **Plano de GND en B.Cu** | Separación de 0.8 mm, ancho mínimo de 0.6 mm, alivios térmicos de 0.6 mm (mínimo 1 radio), sin islas y a 1 mm del borde. Blinda las señales analógicas y reduce lo que fresa la CNC. |
| J22 | Tira de 6 espadines macho | **1 = AI_Y, 2 = GND, 3 = MEDIR_X, 4 = +3.3V, 5 = MEDIR_Y, 6 = AI_X** (orden elegido para que el ruteo quepa en una cara). Cable de 6 hilos hacia J3 de la PCB principal, que debe usar el mismo orden. |

**Sin puentes de alambre.** El ruteo entra completo en una cara.

**C24 (10 µF) salió de la placa 2 y pasa a la PCB principal, junto a J3.** Su pad de GND quedaba encerrado por pistas de otras redes. Además no hace falta aquí: el panel pide pulsos de 4–7 mA, que por un cable de 50 cm producen caídas de menos de 5 mV. C23 (100 nF), pegado al 4066, cubre los transitorios locales.

**Tamaño final:** 52 × 56 mm con esquinas redondeadas, una capa (B.Cu), con las reglas de la sección 1. Las pistas de las señales del panel (X±, Y±) son de 0.6 mm, porque es lo único que cabe para salir entre sus pads. El resto son de 0.8 mm. La placa está en el primer cuadrante y el origen auxiliar de KiCad, que es el origen de los Gerber, está en (0, 0), su esquina inferior izquierda. **Los componentes THT van del lado F (arriba) y se sueldan en B.Cu.** Solo J21 va en B.Cu, porque el cable se apoya en el cobre. Los designadores de la placa 2 empiezan en 21 para no chocar con los de la PCB principal.

### 4.1 Asignación de los interruptores del 74HC4066

Los 4 interruptores del 4066 son bidireccionales e intercambiables. Se eligió esta asignación (variante 83 de la búsqueda con Freerouting) porque es la que rutea en una sola cara sin puentes y respeta el sentido de la corriente que pide la hoja de datos. Eléctricamente es igual al circuito de la sección 5.2.

| Interruptor | Pines | Control | Conecta |
| --- | --- | --- | --- |
| B | 4 ↔ 3 | 5 = MEDIR_X | X+ (pin 4) ← 3.3 V (pin 3) |
| C | 9 ↔ 8 | 6 = MEDIR_X | X− (pin 9) → GND (pin 8) |
| A | 1 ↔ 2 | 13 = MEDIR_Y | Y+ (pin 1) ← 3.3 V (pin 2) |
| D | 10 ↔ 11 | 12 = MEDIR_Y | Y− (pin 10) → GND (pin 11) |

**Por qué este sentido:** la hoja de datos de TI (CD74HC4066, SCHS208E, nota 2 de *Absolute Maximum Ratings*) pide que la corriente del interruptor **entre por los terminales Z (pines 2, 3, 9 y 10)**. Si entra por los terminales Y (1, 4, 8 y 11) con más de 0.6 V de caída, se cuela corriente de V_CC hacia la carga, que aquí es el panel, y se mete error en la lectura. Con el panel medido (310 Ω y 592 Ω), por los interruptores pasan 4–7 mA y la caída llega a ~0.65 V, justo en el límite, así que respetar el sentido sí importa.

Pines de alimentación: 14 = VDD (3.3 V) y 7 = VSS (GND). **El integrado y el zócalo se colocan con la muesca hacia el pin 1**, el pad cuadrado de U21.

### 4.2 Panel táctil medido (26-oct-2026)

- **Cable plano (flex amarillo):** 4 contactos dorados de **0.55 ± 0.05 mm**, separados **0.45 ± 0.05 mm** (medido el 27-oct), o sea **paso de 1.0 mm**. Del primer al último contacto hay ~3.5 mm, y el cable mide ~5.1 mm de ancho.
- **Tolerancia de J21:** los pads miden 0.6 mm (el ancho mínimo de la CNC) y quedan a 0.4 mm entre sí. Un contacto recién toca el pad vecino si el cable se corre **más de 0.4 mm** de lado, y pierde su propio pad si se corre más de 0.55 mm. **Margen de alineación: ±0.4 mm.** Si el paso real fuera 1.05 mm, el error acumulado en los 4 contactos sería de 0.15 mm, dentro de ese margen. Las líneas de serigrafía a los lados de J21 marcan el ancho del cable (5.12 mm) para centrarlo.
- **Numeración:** contactos 1 a 4 contados **de derecha a izquierda**, mirando los contactos dorados de frente, con la punta del cable hacia abajo y el panel arriba.
- **Pares de capas (sin presionar):**
  - contactos **1–3: 310 Ω**, capa **Y**;
  - contactos **2–4: 592 Ω**, capa **X**.

  **Confirmado con la geometría:** la capa que mide en el sentido de los 228 mm tiene barras de 175 mm, o sea R ∝ 228/175 = 1.30. La que mide en el sentido de los 175 mm tiene R ∝ 175/228 = 0.77. La relación esperada es 1.7 y la medida es 592/310 = 1.9, así que la capa de 592 Ω es X (228 mm). Las dos dan ~400–450 Ω por cuadro, un valor normal para paneles resistivos. El signo (+/−) de cada eje se corrige en el software.
- **Panel:** comprado en AliExpress, de 228 × 175 mm, con el cable de 4 hilos saliendo por un lado corto.
- **Presionando con el dedo (multímetro entre las dos capas):** ~5 kΩ en el centro del panel y 0.9–1.6 kΩ cerca del lado del cable. Restando los tramos de capa, la resistencia de contacto queda en ~1–4.5 kΩ, por encima de lo típico según TI (cientos de Ω a ~1 kΩ con un toque firme). Con la pelota puede ser mayor; ver la sección 5.3. Por eso, y porque el nodo de lectura llega cargado del eje anterior, se eligieron C21/C22 = 1 nF y R23/R24 = 220 kΩ (revisión del 27-oct, sección 5.2).

### 4.3 Montaje del cable en J21

```text
   vista lateral (placa 2 con los componentes arriba)
        componentes THT
   ════════════════════════════  placa 2 (cobre B.Cu abajo, pads de J21)
        ▲ contactos dorados del cable mirando HACIA ARRIBA, contra los pads
   ─────────────── cable plano del panel (la punta apunta hacia el 74HC4066)
   ┌───────────────────────────┐ goma o silicona de 1–2 mm
   └───────────────────────────┘ platina rígida (acrílico de 3 mm), apretada con M3 en H21/H22
   El cuerpo del cable se aprieta igual en H23/H24, para que si tiran del cable no se muevan los contactos.
```

- Mirando la placa **desde arriba**, el contacto 1 del cable queda **a la derecha**, sobre el pad 1 (cuadrado). Es la misma orientación de la foto, con el panel arriba y la punta del cable hacia abajo.
- **Antes de fresar,** imprime B.Cu a escala 1:1 y apoya el cable encima para confirmar que los contactos caen sobre los pads.
- **Pads:** estañados finos y **planos** (se nivelan con malla desoldadora) y limpios con alcohol isopropílico.
- **Opcional (gratis):** una **tira de goma conductiva "zebra"** sacada del LCD de una calculadora vieja, entre el cable y los pads, para repartir la presión.
- El cable plano nunca debe quedar tirante ni doblado en ángulo agudo cuando el plato se inclina. El movimiento lo absorbe el cable de 6 hilos de J22.
- **Confirmar con el laboratorio** que la CNC puede fresar los huecos de 0.4 mm entre los pads de J21. Cumple el clearance de 0.3 mm, pero necesita una fresa en V fina.

### IMU en el plato (sin placa propia)

- **Se pone junto al pivote (la cruceta del soporte), no en el borde.** Lejos del pivote, el acelerómetro también mide la aceleración del giro del plato: a = r·α. Con r = 10 cm y un servo que acelera el plato a ~50 rad/s², son ~5 m/s² de error, casi media g. Cerca del centro, ese error es casi cero.
- **Fijación:** al plato con 2 tornillos M3 (el GY-521 trae dos agujeros) y separadores de nylon. Sus ejes X/Y van **paralelos a los ejes de los servos**.
- **Conexión:** se sueldan los **espadines macho** que trae el módulo (VCC, GND, SCL, SDA, XDA, XCL, AD0, INT). Los 4 primeros tienen el mismo orden que J4, así que encima va una carcasa **Dupont hembra de 4 vías** con el cable de 4 hilos trenzado hacia J4. AD0 ya tiene pull-down en el GY-521: la dirección queda en 0x68 sin puente. WHO_AM_I devuelve **0x68**. Si la carcasa Dupont se suelta con la vibración, se asegura con una gota de silicona caliente.

---

## 5. Placa 1 — PCB principal (frente del chasis)

### 5.1 Contenido

| Ref. | Qué | Notas |
| --- | --- | --- |
| J1, J2 | **Tiras hembra de 1 fila, verticales:** J1 = 1×20 (MXP A) y J2 = 1×11 (MXP B), cortadas de tiras hembra de 1×40. Huellas `PinSocket_1x20` / `PinSocket_1x11_P2.54mm_Vertical` | Solo los pines usados, **en el orden que permite rutear en una cara sin puentes** (tablas de la sección 3). Un **jumper Dupont macho–hembra por posición**: la punta hembra al pin del MXP y la macho a la tira. En el esquemático, al lado de cada pin de J1/J2 está escrito el pin del myRIO que llega ahí; se imprime el mapa (`Placa1/mapa_J1_J2`) y se pega junto a la placa. Jumpers de ≤ 30 cm, con cintillos y silicona caliente en las puntas. |
| J3 | Tira de 6 espadines (o JST-XH 6) | Desde J22 de la placa 2, **en este orden: 1 = AI1 (AI_Y, MXP A pin 5), 2 = AGND (pin 6), 3 = DIO0 (MEDIR_X, pin 11), 4 = +3.3V (pin 33), 5 = DIO1 (MEDIR_Y, pin 13), 6 = AI0 (AI_X, pin 3)**. **El 74HC4066 y sus filtros ya no van aquí, sino en la placa 2.** Junto a J3 va **C13 = 10 µF / 16 V** entre +3.3V y AGND, el capacitor de reserva que antes era C24 en la placa 2. |
| J4 | Tira de 4 pines macho | IMU: 3.3V, GND, SCL, SDA (los 4 primeros pines del GY-521, mismo orden). El GY-521 también trae pines macho, así que el cable es **Dupont hembra–hembra de 4 hilos** (una carcasa 1×4 en cada punta, o 4 jumpers H–H pegados con cinta). Asegurar las dos puntas con una gota de silicona caliente. |
| J5, J6 | **Bornera de tornillo de 4 posiciones, paso 3.5 mm** (KF350 / CY350-3.5; 2 + 2 encastradas) | Encoders, en el orden del cable del TorqueNADO: **1 = 5V, 2 = A, 3 = GND, 4 = B**. Se corta el conector del encoder. |
| J7 | **Bornera de 5 posiciones, paso 3.5 mm** (2 + 3 encastradas) | Cytron, en el orden de su entrada: **1 = DIR1, 2 = PWM1, 3 = DIR2, 4 = PWM2, 5 = GND**. |
| R5, R6 | **4.7 kΩ de PWM1 y PWM2 a GND** | Mientras el myRIO arranca, las líneas PWM no quedan flotando y el Cytron no recibe un "100 %" (sección 7.3). |
| J8, J9 | **Bornera de 3 posiciones, paso 3.5 mm** | Servos X e Y. Se corta el conector del MG996R (naranja = señal, rojo = +V, marrón = GND). **J8 = señal, +V, GND; J9 = GND, +V, señal** (invertido a propósito: así +V y GND de los dos servos se rutean sin cruzarse en una cara). La bornera de 3.5 mm aguanta 8 A o más, de sobra para los 2.5 A del servo trabado. |
| R13, R14 | **220 Ω en serie** con las señales de los servos | Si el hilo de señal toca los +6 V del servo (conector mal puesto o cable pelado en la articulación), limitan la corriente hacia la DIO del myRIO. También amortiguan el rebote del cable largo. |
| J10 | Bornera de 2 pines, paso 5.0 mm (KF301 o 301V-5.0-2P) | Entrada de 6 V desde el buck de servos (XL4015, externo): **1 = GND, 2 = +6 V**. |
| C4 | 2200 µF / 16 V | Sobre la entrada de los servos, pegado a J8/J9. |
| J11 | **Bornera de 3 posiciones, paso 3.5 mm** | UART de la RPi: 1 = TX de la RPi (→ RX del myRIO), 2 = RX de la RPi, 3 = GND. |
| J12 | **Bornera de 2 posiciones, paso 3.5 mm** (pos. 1 = VBAT, pos. 2 libre) | **VBAT:** +12 V de la batería, tomado después del interruptor y del fusible de 2 A de la rama del myRIO. **Solo ese hilo**: el GND ya llega por el myRIO, y un segundo hilo de GND cerraría un lazo de tierra. |
| R11, R12, C14 | 22 kΩ / 6.8 kΩ / 100 nF | Divisor de VBAT hacia AI2 (MXP A pin 7): 14.5 V (carga completa) → 3.42 V; 10 V (descargada) → 2.36 V. Paso del ADC: 5.2 mV de batería. Aunque R12 se abriera, AI2 vería ≤ 16 V, el máximo que soporta. |

**Nada externo se suelda directo a la PCB:** todo entra por espadines, JST o borneras, y U1 va en zócalo. Así cualquier pieza se cambia sin desoldar.

**Llevar la alimentación de los servos por la PCB (mi decisión):** el cable del servo trae los tres hilos en un solo conector. Si la alimentación no pasara por la placa, habría que cortar el cable o hacer un empalme. Por eso entra por J10 y sale por J8/J9, en una **zona de potencia separada** (sección 5.5) con pistas de **3 mm**. Con cobre de 35 µm, eso aguanta los picos de 5 A de los dos MG996R con un calentamiento bajo, y el recorrido es de pocos centímetros.

### 5.2 Circuito del panel (va en la placa 2)

Es el mismo de la revisión anterior, que ya estaba verificado, con lógica a 3.3 V. En la placa 2, el +3.3 V, AGND, AI0/AI1 y MEDIR_X/MEDIR_Y llegan por J22 desde el MXP A. En el dibujo, U1, R1–R4 y C1–C3 corresponden a U21, R21–R24 y C21–C23 de la placa 2:

```text
                       +3.3 V (MXP A pin 33)
                         │
                    ┌────┴──────────────────────────────────┐
                    │ 14 VCC        74HC4066                 │   C3 100 nF entre pin 14 y pin 7
  X+ ───────────────┤ 1  SW-A  2 ├──── +3.3 V               │   SW-A: X+ → 3.3 V
                    │ 13 ctrl-A    ◄── MEDIR_X (DIO0)       │
  X− ───────────────┤ 4  SW-B  3 ├──── GND                  │   SW-B: X− → GND
                    │ 5  ctrl-B    ◄── MEDIR_X (DIO0)       │
  Y+ ───────────────┤ 8  SW-C  9 ├──── +3.3 V               │   SW-C: Y+ → 3.3 V
                    │ 6  ctrl-C    ◄── MEDIR_Y (DIO1)       │
  Y− ───────────────┤ 11 SW-D 10 ├──── GND                  │   SW-D: Y− → GND
                    │ 12 ctrl-D    ◄── MEDIR_Y (DIO1)       │
                    │ 7  GND                                 │
                    └────────────────────────────────────────┘

  Lectura de X:  Y+ ──┬── R1 1 kΩ ──┬──► AI0 (MXP A pin 3)
                      │             └── C1 1 nF ── AGND  
                      └── R3 220 kΩ ── AGND

  Lectura de Y:  X+ ──┬── R2 1 kΩ ──┬──► AI1 (MXP A pin 5)
                      │             └── C2 1 nF ── AGND  
                      └── R4 220 kΩ ── AGND
```

Secuencia de lectura (en LabVIEW, cada 2–5 ms):

```text
MEDIR_Y = 0;  MEDIR_X = 1;  esperar 1 ms;  vx = AI0
MEDIR_X = 0;  MEDIR_Y = 1;  esperar 1 ms;  vy = AI1
MEDIR_Y = 0
tocado = (vx > 0.2 V) y (vy > 0.2 V)   # lectura minima valida: X 0.42 V, Y 0.65 V
x_mm = (vx - vx_min) / (vx_max - vx_min) * 228      # calibrar con la pelota en las esquinas
y_mm = (vy - vy_min) / (vy_max - vy_min) * 175
```

Nunca deben estar las dos capas polarizadas a la vez: primero se apaga una y después se enciende la otra.

**Por qué C21/C22 = 1 nF y R23/R24 = 220 kΩ (revisión del 27-oct-2026):**

| Situación | Cuenta | Resultado |
| --- | --- | --- |
| Con pelota: el nodo pasa del valor anterior al nuevo | τ = (R21 1 kΩ + contacto 1–5 kΩ + capa ~0.3 kΩ) × 1 nF ≈ 2–6 µs | Asienta en < 0.05 ms; 1 ms sobra. |
| Sin pelota: el nodo viene cargado a ~3.3 V del eje anterior | τ = (220 kΩ ∥ ~500 kΩ del myRIO) × 1 nF ≈ 0.15 ms; baja a 0.2 V en 2.8τ ≈ 0.43 ms | Se detecta "sin pelota" antes de 1 ms. |
| Carga sobre la lectura | Error ≈ R_contacto / (153 kΩ + R_contacto) | 0.7 % con 1 kΩ y 3.5 % con 5 kΩ. |
| Fuga del 4066 apagado (máx. 0.1 µA a 25 °C) | 0.1 µA × 220 kΩ | ≤ 22 mV, contra 0.42 V de lectura mínima válida. |
| Corriente por los interruptores | X: 3.3 V / (592 + 2·100) ≈ 4.2 mA; Y: 3.3 V / (310 + 2·100) ≈ 6.5 mA | Caída de hasta ~0.65 V: por eso la corriente entra por los pines Z. |
| Rango de lectura | X: 0.42–2.88 V (2.47 V); Y: 0.65–2.65 V (2.0 V) | ~0.11 mm por paso del ADC de 12 bits (0–5 V). |

**Errores que se evitaron:** con 100 nF + 100 kΩ (plan original) o 10 nF + 330 kΩ, el nodo tardaba 2–8 ms en descargarse sin pelota, y a 1 ms el software habría leído ~2–3 V, una pelota fantasma. Por la misma razón, **la PCB principal no lleva capacitores en AI0/AI1** (C11/C12 se eliminaron): cualquier capacitor extra se suma al nodo.

**Software:** esperar 1 ms después de conmutar, promediar 8 lecturas (el filtro RC queda en ~25 kHz y el ruido de los motores se baja promediando) y usar 0.2 V como umbral de "sin pelota".

### 5.3 Detección de la pelota en el myRIO (todo ajustable en el software)

La placa no depende de la pelota: los umbrales son **controles en el panel frontal de LabVIEW** y se ajustan cuando llegue la pelota real. Se eligió la versión de **6 pines** (2 líneas de control, MEDIR_X y MEDIR_Y), que no mide la presión Z1. La pelota se detecta por umbral; un contacto débil no se descarta, solo se ve como una lectura algo más baja.

| Control | Valor inicial | Para qué |
| --- | --- | --- |
| `V_MIN` | 0.2 V | Si X o Y bajan de este valor, no hay pelota. Sin pelota, R23/R24 llevan la lectura a 0 V en menos de 0.5 ms. La lectura mínima válida es 0.42 V en X y 0.65 V en Y. |
| `T_ESPERA` | 1 ms | Espera después de conmutar MEDIR_X / MEDIR_Y. |
| `N_FILTRO` | 3 | Mediana de 3, o promedio de las 2 lecturas más cercanas (TI SBAA155A, sección 4). |
| `SALTO_MAX` | por calibrar | Descarta muestras que se alejan demasiado de la anterior: rebotes o contacto intermitente. |
| `N_CONFIRMA` | 2–3 | Número de lecturas seguidas sobre `V_MIN` que hacen falta para dar la pelota por presente. |

**Calibración cuando llegue la pelota:**

1. Sin pelota, anota X e Y. Deben quedar cerca de 0 V.
2. Con la pelota quieta en 9 puntos del panel (esquinas, centros de lado y centro), anota X e Y en voltios.
3. Ajusta la conversión de voltios a milímetros con esos 9 puntos (bilineal o polinomio de 2.º orden). Así se corrigen la no linealidad del panel, la R_ON del 4066 y la pequeña carga de R23/R24 (~3 % con 5 kΩ de contacto).
4. Verifica qué capa es X (la de 592 Ω, a lo largo de los 228 mm) y el signo de cada eje. Si alguno sale al revés, se corrige en el software.
5. Antes de soldar, mide con el multímetro, **con la pelota apoyada en el centro**, la resistencia entre los contactos 1 y 2:
   - **< 20–30 kΩ:** la detección funciona bien.
   - **Abierto o cientos de kΩ:** la pelota es muy liviana. Hay que usar una más pesada, por ejemplo de acero.

**Si más adelante se quiere medir la presión (Z1):** hacen falta 4 líneas de control independientes (X+, X−, Y+ e Y− por separado) y J22 de 8 pines. Se probó el 27-oct: en una cara quedaban 3–4 cruces y uno no tenía espacio para los huecos del puente, así que no se usó.

### 5.4 Reglas de ruteo (una cara, sin vías)

1. **J1/J2 en el borde superior**, con una franja de ~3.4 mm entre las tiras y el borde reservada al plano de GND (sin pistas). Por esa franja y por los pads de DGND de las tiras ("compuertas") el plano llega a los pasillos entre grupos de pistas: los GND del medio de las borneras (encoders, IMU) y los de R5/R6.
2. **Debajo de cada compuerta** hay un área de 2.6 × 5.6 mm sin pistas, para que el plano entre por ahí aunque las pistas pasen pegadas.
3. **Borneras en los bordes** con la entrada del cable hacia afuera: UART y encoder 1 a la izquierda, Cytron/VBAT/servos abajo, encoder 2 e IMU a la derecha. El orden de cada tira sigue el de sus destinos, así no se cruza ninguna pista.
4. **Puentes de alambre:** ninguno.
5. **Señales:** 0.8 mm. **Potencia de servos:** 3 mm donde cabe y 2.5 mm en el resto (un cuello de 1.9 mm junto a un pad). **GND:** plano en B.Cu con conexión sólida a los pads (sin alivio térmico: en los pasillos angostos solo salía un rayo).
6. **Tamaño final: 95 × 65 mm** (se compactó en Y; con menos altura ya no rutea en una cara). Ruteo hecho con Freerouting solo en B.Cu y verificado con el DRC de `Placa1.kicad_dru`: 0 errores, 0 sin rutear y paridad 0 con el esquemático. Scripts en `Electronica/Placa1/scripts/`.

### 5.5 Tierras

- **Zona de potencia de los servos:** J10 (GND) → J8/J9 (GND), C4 negativo. Es una isla de cobre propia.
- **Zona del panel:** en la PCB principal, el GND de J3. Va a **AGND** (MXP A pin 6). En la placa 2, todo su GND es el del panel y llega por J22.
- **Zona digital:** todo lo demás, con DGND de J1 y J2.
- Las tres se unen en **un solo punto**, junto a J10 o al DGND de J1. Así la corriente de los servos no pasa por la tierra del panel.

---

## 6. Componentes con alternativa

| Componente | Primera opción | Alternativa |
| --- | --- | --- |
| Switch analógico | 74HC4066 a 3.3 V (~70–100 Ω por interruptor) | CD4066 a 3.3 V: funciona, pero su resistencia sube a ~0.5–1 kΩ y el rango de lectura se reduce a ~0.6–2.7 V. Se compensa calibrando. **No alimentarlo a 5 V**: necesitaría 3.5 V para leer un "1" y el myRIO da 3.3 V. |
| IMU | **MPU-6050 (módulo GY-521)**, el que se usa | MPU9250/MPU6500 (GY-9250): mismo conector y misma dirección 0x68; WHO_AM_I = 0x71 (9250) o 0x70 (6500). Para el plato solo se usan el acelerómetro y el giroscopio. |

---

## 7. Distribución de energía

### 7.1 Esquema

```text
Batería TETRIX 12 V NiMH 3000 mAh (fusible interno de 20 A)
   │
Interruptor
   │
Bornera de distribución (+12 V) / bornera GND (punto estrella)
   ├── fusible en línea 2 A ── Schottky SB560 (o 1N5822) ──┬── myRIO (6–16 V)
   │                                                       └── C 1000 µF / 25 V a GND
   ├── fusible en línea 10 A ── Cytron MDD10A ── motores (100 nF cerámico en los bornes de cada motor)
   └── fusible en línea 5 A ── Buck XL4015 (5 A) @ 6.0 V ── J10 de la PCB (servos)
GND: todos los GND llegan a la bornera estrella, sin encadenarse.

RPi 3B + Brio: batería portátil USB por micro-USB, separada de la batería TETRIX.
```

### 7.2 Notas

- **Fusibles en línea de cuchilla** (portafusibles de autopartes). Son baratos y no necesitan caja.
- **Diodo Schottky + 1000 µF en la rama del myRIO:** si los motores hacen caer el voltaje un instante, el diodo evita que el capacitor se descargue hacia los motores, y el myRIO aguanta esos milisegundos. El diodo baja ~0.5 V, que no importa con 12 V.
- **Voltaje de los servos, 5 o 6 V:** el MG996R acepta de 4.8 a 7.2 V. A 6 V da más torque (~11 kg·cm, contra ~9.4 a 4.8 V) y es más rápido, lo que ayuda en la pendiente. **Ojo:** la planta del plato (`Control_Plato/planta_plato.mat`) se identificó con los servos a 6 V. Si cambian a 5 V, el servo se vuelve más lento y **hay que repetir los ensayos de escalones**. Recomiendo 6 V. El buck es ajustable, así que la decisión no cambia la PCB.
- **El buck se ajusta con el multímetro, sin carga**, **antes** de conectar los servos.
- **Buck de servos = XL4015 (5 A), fuera de la PCB** (revisión del 27-oct). Hace falta un buck: los MG996R no aceptan 12 V, y el +5 V del myRIO da solo 100 mA por conector. Cada MG996R consume 0.5–0.9 A moviéndose y **2.5 A trabado** (hoja de datos, a 6 V). En uso normal los dos piden 1–2 A, dentro de los 4.5 A continuos recomendados del XL4015. Solo con los dos servos trabados a la vez llegan a 5 A, el máximo del módulo, que se protege con su límite de temperatura. **Si el módulo trae dos potenciómetros (CV y CC), ajustar el CC a ~4.5 A.** Se descartó el XL4016 (8 A) porque es mucho más grande (65 × 48 mm). **Va atornillado al chasis junto a la PCB, no sobre ella:** se calienta y su conmutación quedaría al lado de las señales analógicas del panel. Del buck a J10: cable de 18–20 AWG, lo más corto posible. **No tiene protección contra polaridad invertida:** revisar los colores antes de conectar.
- **Motores TorqueNADO:** 8.7 A trabados cada uno (hoja de Pitsco), 17.4 A los dos. El Cytron MDD10A aguanta 10 A continuos por canal, y el fusible de 10 A de su rama corta antes de que se queme el de 20 A de la batería si los dos motores quedan trabados.
- **Medición de la batería (J12 → AI2):** el hilo de VBAT sale de la rama del myRIO **después** del fusible de 2 A, así queda protegido. En LabVIEW: VBAT = AI2 / 0.236. NiMH de 10 celdas: 13–14.5 V cargada, ~12 V nominal y **10 V vacía** (no bajar de ahí). Sirve también para escalar el PWM de los motores con el voltaje real de la batería.
- **RPi con batería portátil:** tiene que dar **≥ 2.5 A** a 5 V, porque la RPi 3B con la Brio consume ~2 A. Con una de 2.1 A aparece el aviso de bajo voltaje (el rayo en pantalla, o `vcgencmd get_throttled` ≠ `0x0`). Usa un cable micro-USB corto y grueso. **El hilo GND de J11 es obligatorio:** es la única referencia común entre la RPi y el myRIO, y sin él el UART no funciona.
- **Autonomía aproximada de la batería TETRIX:** myRIO ~0.5–1 A + servos ~1 A a 12 V + motores. Con 3000 mAh, alcanza para unos 30–60 minutos de pruebas.

### 7.3 Por qué el myRIO se desconectaba con la fuente de 12 V / 3 A (hipótesis, verificar)

**Síntoma:** pasaba solo al correr el programa, justo al inicio. Con el cargador del myRIO por separado, no pasaba.

**Hipótesis** (el manual de NI confirma la primera parte: las DIO 0–13 tienen pull-up de 40 kΩ y "flotan en la dirección del pull" al arrancar): mientras el myRIO carga el programa y el FPGA, las DIO del MXP son entradas con pull-up interno. Así, PWM y DIR del Cytron quedan en "1", y los dos motores arrancan **al 100 % al mismo tiempo**. Esa corriente supera los 3 A de la fuente, el voltaje cae por debajo de los 6 V y el myRIO se reinicia. Con el cargador, el myRIO no compartía la fuente que caía.

**Cómo verificarlo:**

1. Con las ruedas en el aire, corre el programa con la configuración que fallaba. Si las ruedas dan un tirón al inicio, se confirma.
2. Otra forma: con el myRIO encendido pero sin programa corriendo, mide el voltaje del pin PWM0 (MXP A pin 27) respecto a GND. Si da ~3.3 V, se confirma.

**Corrección**, que sirve aunque la causa resulte ser otra:

- R5/R6 de pull-down en la PCB,
- el diodo y el capacitor de la sección 7.2,
- en LabVIEW, escribir PWM = 0 antes de habilitar el motor y usar **rampas** de PWM, sin saltos de 0 a 100 %.

---

## 8. Cronograma y pruebas (dom 25 → jue 29 de octubre)

| Día | Qué | Listo cuando |
| --- | --- | --- |
| **Dom 25 / Lun 26** | **1. Panel con multímetro:** medir el **paso** del cable (con vernier, del primer al último contacto, dividido entre 3) e identificar X± e Y±. En el mismo eje hay una resistencia fija de ~200–900 Ω; entre ejes distintos está abierto sin toque. **Prueba de peso:** con la pelota encima, medir entre X+ e Y+; si sigue en OL, la pelota es muy liviana y hay que usar una más pesada. | Paso, asignación de pines y pelota definidos. |
| **Lun 26** | **2. Compras** (sección 9). **3. Prueba del arranque:** paso 2 de la sección 7.3. | — |
| **Lun 26** | **4. Prototipo en placa perforada:** adaptador QFP con abrazadera + circuito del 74HC4066. Prueba con el ESP32 (`Pruebas_Arduino/PruebaPanel/PruebaPanel.ino`): primero en modo `DIRECTO`, después en modo `SWITCH`. | Lecturas X/Y estables y "sin pelota" en 0 V. |
| **Mar 27** | **5. Diseño de la PCB principal y del adaptador** con las reglas de la sección 1. Imprimir a 1:1 y comprobar las huellas con los componentes reales. | DRC sin errores y pin 1 de J1/J2 verificado desde arriba. |
| **Mié 28** | **6. Entregar los diseños a la CNC.** Mientras tanto: armar la distribución de energía y ajustar el buck de servos sin carga. | Buck al voltaje elegido (6.0 V recomendado). |
| **Jue 29** | **7. Soldar y probar:** continuidad pin a pin de J1/J2 contra la sección 3, con los jumpers puestos. Encender **sin el myRIO** y medir el voltaje de los servos en J8/J9. Después conectar el myRIO, medir 3.3 V en J4 y 5 V en J5/J6, y probar un dispositivo a la vez: encoders → Cytron (ruedas en el aire) → servos → panel → IMU (leer WHO_AM_I) → UART de la RPi. | Cada dispositivo se lee o se mueve desde LabVIEW. |

---

## 9. Lista de compras

Precios aproximados en soles. Verifica el stock antes de ir. La cantidad "a comprar" incluye repuestos para lo que se puede quemar o perder al soldar.

### 9.1 Placa 2 (adaptador + conversor del panel)

Sale del BOM de KiCad (`Electronica/Placa2/Placa2_BOM.csv`, 27-oct-2026). Todo es through-hole. La versión para llevar a la tienda, con los códigos de color de las resistencias y los códigos de los capacitores, está en `Electronica/Lista_compras.csv`.

| # | Ref. | Componente | En la placa | A comprar | Aprox. (S/) | Dónde | Notas |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | U21 | **74HC4066** en DIP-14: NXP 74HC4066N o TI CD74HC4066E | 1 | **2** | 2–4 c/u | Jr. Paruro, Naylamp | **No comprar 74HCT4066**: no funciona a 3.3 V. Si no hay, sirve el CD4066BE, con más R_ON; se corrige calibrando. |
| 2 | — | Zócalo DIP-14 | 1 | 2 | 1 c/u | Jr. Paruro | El integrado va en zócalo. |
| 3 | R21, R22 | Resistencia **1 kΩ**, película metálica 1 %, 1/4 W | 2 | 4 | 0.2 c/u | Jr. Paruro | 5 bandas: marrón-negro-negro-marrón, tolerancia marrón. |
| 4 | R23, R24 | Resistencia **220 kΩ**, película metálica 1 %, 1/4 W | 2 | 4 | 0.2 c/u | Jr. Paruro | Pull-downs. 5 bandas: rojo-rojo-negro-naranja, tolerancia marrón. |
| 5 | C21, C22 | Capacitor **1 nF cerámico C0G (NP0) o X7R**, código **102**, patas con paso de 5 mm | 2 | 4 | 0.3 c/u | Jr. Paruro | No usar 10 nF ni 100 nF (ver sección 5.2). |
| 6 | C23 | Capacitor **100 nF cerámico X7R** (código **104**), patas con paso de 5 mm | 1 | 2 | 0.3 c/u | Jr. Paruro | Desacople del 74HC4066. |
| 7 | J22 | Tira de **6 espadines macho** de 2.54 mm, recta | 1 | 1 tira de 40 | 1–2 | Jr. Paruro | Se corta a 6. |
| 8 | — | Cable flexible de 6 hilos (~60 cm) + 2 carcasas Dupont hembra 1×6 con sus terminales (o JST-XH 6) | — | 1 + 2 | 5–10 | Jr. Paruro | De J22 a J3 de la PCB principal. Hay que respetar el orden de pines. |
| 9 | J21 | Contacto a presión: **no se compra**, son los pads de cobre fresados | — | — | — | — | Ver los ítems 10 y 11 para la abrazadera. |
| 10 | H21–H24 | Abrazadera del cable: **2 platinas de acrílico de 3 mm, ~35 × 8 mm**, cada una con 2 agujeros de 3.2 mm **separados 27 mm**, y una **tira de goma o silicona** de 1–2 mm (~10 × 6 mm por platina) | — | 2 (+1) + 1 | 3–6 | Ferretería, tiendas de acrílico | H21/H22 aprietan los contactos contra los pads; H23/H24 aprietan el cuerpo del cable para que no se muevan los contactos. La goma va solo bajo el cable. |
| 11 | H21–H24 | **Tornillos M3 × 12 mm** de cabeza redonda + **tuercas M3 autoblocantes (nylock)** + 2 arandelas planas por tornillo | 4 | 6 + 6 + 10 | 3–5 | Ferretería | El tornillo entra por arriba (lado de los componentes) y la tuerca va abajo, contra la platina. Apretar suave y parejo. |
| 11b | H25, H26 | **Tornillos M3 × 20 mm** + tuerca + 2 arandelas | 2 | 2 + 2 + 4 | 2–3 | Ferretería | Fijan la placa al plato, a través de los separadores. |
| 12 | H25, H26 | **Separadores de nylon M3 de 10 mm** | 2 | 4 | 2–4 | Naylamp, ferretería | Debajo de la placa quedan la goma (1–2 mm), el acrílico (3 mm) y la tuerca (~2.4 mm), unos 7 mm: hace falta espacio sobre el plato. |
| 13 | — | **Placa de cobre de una cara**, FR-4 (o FR-1), de al menos 60 × 65 mm | 1 | 2 | 3–6 c/u | Jr. Paruro | Si no la da el laboratorio. La placa mide 52 × 56 mm. |
| 14 | — | Malla desoldadora + alcohol isopropílico | — | 1 + 1 | 5–10 | Jr. Paruro | Para dejar planos y limpios los pads de J21. |
| 15 | — | *(Opcional, gratis)* tira de goma conductiva **"zebra"** de un LCD viejo | — | 1 | 0 | Calculadora o teléfono fijo viejo | Reparte la presión sobre los contactos. |

### 9.2 PCB principal, energía y cableado

| # | Componente | Cant. | Aprox. (S/) | Dónde |
| --- | --- | --- | --- | --- |
| 16 | Resistencias 1/4 W: 4.7 kΩ ×2 (R5/R6), 220 Ω ×2 (R13/R14), 22 kΩ ×1 (R11), 6.8 kΩ ×1 (R12) | 6 (+ repuestos) | 2–3 | Jr. Paruro |
| 17 | Capacitores cerámicos 100 nF (C14 y desacoples varios). **Sin capacitores en AI0/AI1** (C11/C12 eliminados de la placa el 27-oct) | 4 | 1–2 | Jr. Paruro |
| 18 | **C13 = electrolítico 10 µF / 16 V** junto a J3: es el capacitor de reserva del 3.3 V que salió de la placa 2 | 2 | 0.5 c/u | Jr. Paruro |
| 19 | Electrolíticos 2200 µF / 16 V (servos) y 1000 µF / 25 V (myRIO) | 1 + 1 | 4–8 | Jr. Paruro |
| 20 | Diodo Schottky SB560 o 1N5822 (rama del myRIO) | 2 | 1–2 c/u | Jr. Paruro |
| 21 | **Jumpers Dupont macho–hembra de 20 cm** (myRIO ↔ J1/J2: 24 señales + al menos 4 GND = 28; hasta 31) + jumpers hembra–hembra (IMU) | 40 M–H + 10 H–H | 10–15 | Naylamp, Electromanía, Jr. Paruro |
| 22 | **Tira hembra de 1 fila × 40, 2.54 mm**, recta: se cortan 1×20 (J1) y 1×11 (J2) | 2 | 1–2 c/u | Naylamp (Header hembra 40 pin), Electromanía, Jr. Paruro |
| 23 | **Borneras de tornillo de paso 3.5 mm (KF350 / CY350-3.5) de 2 y 3 posiciones**, encastrables: 2 + 2 (×2, encoders), 2 + 3 (Cytron), 3 (×3, servos y UART), 2 (VBAT); y carcasas Dupont hembra 1×4 (IMU) y 1×6 (panel) | ~10 de 2 + ~5 de 3 | 10–20 | Electromanía (CY350-3.5), Jr. Paruro |
| 24 | Tiras de pines macho y hembra de 2.54 mm | 2 + 2 | 1–2 c/u | Jr. Paruro |
| 25 | Borneras de 2 pines paso 5.0 mm (KF301 / 301V-5.0-2P) + barras de distribución | 4 + 2 | 5–10 | Electromanía, Jr. Paruro |
| 26 | **Buck XL4015 de 5 A** (servos), 54 × 23 mm | 1 | 15 | En stock según el usuario (27-oct); Electromanía figuraba agotado |
| 27 | Batería portátil USB 5 V **≥ 2.5 A** (RPi) + cable micro-USB corto y grueso | 1 + 1 | si ya la tienen, 0 | — |
| 28 | Portafusibles en línea de cuchilla + fusibles mini de 2, 5 y 10 A | 3 + juego | 10–20 | Autopartes |
| 29 | Cable siliconado 16–18 AWG (rojo/negro) | 2 m | 5–10/m | Jr. Paruro, tiendas de RC |
| 30 | Cable flexible de 4 hilos (IMU) | 1 m | 2–5 | Jr. Paruro |
| 31 | Termocontraíble y cintillos | — | 5–10 | Jr. Paruro |
| 32 | Placa de cobre de una cara para la PCB principal (≤ 10 × 10 cm), si no la da el laboratorio | 1 | 5–10 | Jr. Paruro |

**Ya no se compran:** el adaptador SMD→DIP QFP de 0.8 mm (el cable del panel resultó de 1.0 mm y se aprieta directo contra pads fresados) ni la placa perforada para el adaptador. La placa perforada solo hace falta si quieres probar el circuito del 4066 con el ESP32 antes de tener la placa fresada.

**Calibre de cable:** batería → Cytron → motores: 16–18 AWG. Ramas del myRIO, los bucks y los servos: 20–22 AWG. Señales: 24–26 AWG.

---

## 10. Queda para quien diseña (no cambia lo que se construye)

- El programa para dibujar la PCB (KiCad, EasyEDA u otro). Solo debe aceptar las reglas de la sección 1.
- La posición exacta de cada conector en la PCB, según por dónde lleguen los cables en el chasis.
- El tipo de conector de alimentación del myRIO: el del cargador original o una bornera adaptada.
