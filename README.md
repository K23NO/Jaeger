# Jaeger

Differential-drive mobile robot (TETRIX MAX) with a two-degree-of-freedom ball-balancing platform,
used to study the transport of an unsecured load. Course project of Mechatronic Systems Design
(MT5001), Universidad de Ingeniería y Tecnología (UTEC), Lima, 2026-2.

Authors: Flavia Sofía Díaz Follegatti, Flavia Luciana Palacios Davalos, Brenda De la Cruz Menacho,
Kenyi Reyes De Lama.

## System

| Unit | Role |
|---|---|
| NI myRIO-1900 (LabVIEW 2019) | Runs both control loops: cascaded speed/position control of the base every 10 ms and two-axis PID of the ball position at the camera rate |
| Raspberry Pi 3 + Logitech Brio | Detects the ball at 60 fps and sends `x, y` in mm to the myRIO over UART (230 400 baud) |
| ESP32 (bench only) | Logged the motor and servo step responses used for plant identification |

## Repository layout

```
hardware/
  pcb_myrio_interface/      KiCad project, BOM, STEP and Gerber/drill files of the interface board (board 1)
  pcb_touch_panel_unused/   Touch-panel interface board (board 2); designed but not used in the final prototype
  mechanical/               Exploded-view drawings of the assembly
software/
  myrio_labview/            LabVIEW project (Main.vi): base and plate controllers, logging
  raspberry_vision/         Ball detection, px-to-mm calibration, UART sender, setup script and service
  esp32_bench/              Arduino sketches and Python loggers for plant identification
data/
  identification_motors/            Motor speed response to PWM steps (2026-10-17)
  identification_plate_servos/      Plate tilt response to servo steps (2026-10-19)
  integration_2026-11-17/raw/       LabVIEW logs of the integrated trials (level-floor routine and 10° ramp)
  integration_2026-11-17/clean/     Same logs as CSV with headers fixed and time aligned to the first base set-point
analysis/                   Scripts that produce the figures and metrics of the report
docs/                       Design notes (electronics plan, camera setup, UART protocol, PID review)
```

3D-printable and laser-cut parts of the balancing platform: Mendeley Data,
doi:[10.17632/638z9y6dd9.1](https://doi.org/10.17632/638z9y6dd9.1).

## Data notes

* Plate logs: the LabVIEW header is shifted. Ball position is in columns `inclinacion_x` (x, mm) and
  `inclinacion_y` (y, mm); `erro_x`/`error_y` repeat them because the reference is 0.
* Plate logs have no time column and their period varies between runs (9–15 ms), so plate and base
  logs are not aligned in time.
* Metrics discard the first 300 plate samples after the ball is first detected (ball placement).

## Licenses

Software: MIT (`LICENSE`). Hardware design files and documentation: CC BY 4.0 (`LICENSE-hardware.md`).
