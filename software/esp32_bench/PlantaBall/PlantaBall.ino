// ========== PLANTA DEL PLATO (ESP32 DevKit) ==========
// Identificacion de la planta del plato en lazo abierto (sin controlador):
//   alpha_cmd (angulo pedido al plato) -> alpha_imu (angulo medido)
// Dos ejes, un servo por eje. Requiere la libreria ESP32Servo.
//
// Comandos (Monitor Serie a 115200, fin de linea "Nueva linea"):
//   ?            estado: centros, offsets y angulos actuales
//   N            nivelar con el IMU (ajusta el centro de cada servo)
//   TX,1520      fijar el centro del servo X en us (TY,... para el Y)
//   Z            el plato esta nivelado ahora: cero del IMU
//   C            calibrar los potenciometros (barrido del servo de -20 a +20 grados)
//   G            guardar la calibracion en la memoria del ESP32
//   P,2,-1       llevar el plato a alphaX = 2, alphaY = -1 grados
//   E,X,2        escalones de 2 grados en el eje X (X, Y o A = ambos)
//   W,Y,2,1.5    seno de 2 grados y 1.5 Hz en el eje Y
// Lazo cerrado (PI del angulo con el IMU, ganancias de disenar_control_plato.m):
//   K,X,0.27,8.8,0   ganancias kp, ki, kd del eje X (K,A,... para los dos)
//   R,X,2        escalones en lazo cerrado (como E, pero alpha_ref -> PI)
//   S,Y,2,1.5    seno en lazo cerrado (como W)
//
// Los experimentos se guardan en memoria y al terminar se imprimen en CSV:
//   t_ms,ax_cmd,ay_cmd,thx_cmd,thy_cmd,thx_pot,thy_pot,ax_imu,ay_imu,gx,gy,ax_ref,ay_ref
// En lazo abierto ref = cmd; en lazo cerrado cmd es la salida del PI.
// Para guardarlos en la PC: python capturar_plato.py
//
// Convencion de signos: alpha_cmd positivo debe dar alpha_imu positivo.
// El comando N lo revisa y avisa si hay que cambiar algun signo.
// Todos los mensajes empiezan con '#' para separarlos de los datos.

#include <Wire.h>
#include <ESP32Servo.h>
#include <Preferences.h>
#include <math.h>

// ---------------- Pines ----------------
// MPU6050 en el I2C por defecto del DevKit: SDA = GPIO21, SCL = GPIO22.
// Potenciometros en pines del ADC1 (GPIO32-39), se definen en ejes[].

// ---------------- Servo ----------------
const float US_PER_DEG = 11.11f;      // aprox. 500-2500 us en 180 grados
const int US_MIN = 500;
const int US_MAX = 2500;
const float CENTRO_MAX_US = 500.0f;   // el centro no se aleja mas de esto de 1500

// ---------------- Potenciometro ----------------
// Cable soldado al cursor (pin central) del potenciometro de cada servo.
// El ESP32 lee de 0 a ~3.1 V: medir con el multimetro antes de conectarlo.
const bool USAR_POT = true;           // false si no estan conectados
const float POT_CAL_DEG = 20.0f;      // C recorre el servo de -20 a +20 grados
const int POT_PUNTOS = 9;             // puntos del barrido de calibracion

// ---------------- IMU ----------------
const int MPU_ADDR = 0x68;
const bool IMU_EJES_CRUZADOS = false; // true si el eje X del plato es el pitch del IMU
const float FILTRO = 0.98f;           // filtro complementario
const float GYRO_LSB = 65.5f;         // LSB por grado/s con rango +/-500

// ---------------- Experimentos ----------------
const uint32_t TS_US = 10000;         // periodo de muestreo: 100 Hz
const float TS_S = TS_US / 1000000.0f;
const float ALPHA_SAT_LC = 10.0f;     // lazo cerrado: limite de alpha_cmd [grados]
const float T_ESCALON_S = 1.5f;       // duracion de cada tramo
const float SEQ_ESC[] = {0, 1, 0, -1, 0, 2, 0, -2, 0};   // multiplicadores de amp
const int N_ESC = sizeof(SEQ_ESC) / sizeof(SEQ_ESC[0]);
const float T_SENO_S = 10.0f;
const float T_QUIETO_S = 0.5f;        // en cero antes y despues del seno
const int MAX_MUESTRAS = 1400;

// ---------------- Ejes ----------------
struct Eje {
  char nombre;
  int pinServo;
  int pinPot;
  int signoServo;     // cambiar a -1 si el plato gira al reves
  int signoImu;       // cambiar a -1 si el IMU mide con el signo invertido
  float rBrazo;       // radio del brazo del servo [m]
  float rPlato;       // distancia del pivote a la biela en el plato [m]

  // Calibracion (se guarda con G)
  float centroUs;     // pulso con el plato nivelado
  float potMvA;       // mV del potenciometro con el servo a -POT_CAL_DEG
  float potMvB;       // mV del potenciometro con el servo a +POT_CAL_DEG
  float offsetImu;    // lectura del IMU con el plato nivelado

  // Control PI(D) del angulo (se guarda con G)
  float kp;           // [grados de cmd / grado de error]
  float ki;           // [1/s]
  float kd;           // [s], derivada con el giroscopio

  // Estado
  float integ;        // integral del PI [grados]
  float anguloCrudo;  // salida del filtro complementario [grados]
  float sesgoGyro;
  float gyro;         // [grados/s] sin sesgo
  float thetaCmd;     // ultimo angulo enviado al servo
  Servo servo;
};

// Geometria: sin(alpha) = (rBrazo / rPlato) sin(theta)
// Medido: brazo del servo 35 mm, pivote del plato a la biela 59 mm (K = 0.593).
Eje ejes[2] = {
  // nombre, servo, pot, signoServo, signoImu, rBrazo, rPlato,
  // centroUs, potMvA, potMvB, offsetImu, kp, ki, kd
  // signoImu = -1: en la prueba de senos (2026-10-19) el IMU salia invertido
  // en los dos ejes (fase ~150 grados respecto a lo pedido).
  // kp, ki: PI de disenar_control_plato.m (margen de fase 60 grados).
  {'X', 18, 34, 1, -1, 0.035f, 0.059f, 1500.0f, 1000.0f, 2000.0f, 0.0f, 0.2744f, 8.821f, 0.0f},
  {'Y', 19, 35, 1, -1, 0.035f, 0.059f, 1500.0f, 1000.0f, 2000.0f, 0.0f, 0.4046f, 10.02f, 0.0f},
};

struct Muestra {
  float t_ms;      // tiempo real desde la primera muestra
  float axCmd, ayCmd, thxCmd, thyCmd, thxPot, thyPot, axImu, ayImu, gx, gy;
  float axRef, ayRef;
};

Muestra buf[MAX_MUESTRAS];

Preferences prefs;
uint32_t proximoTick = 0;
uint32_t ultimoImuUs = 0;
uint32_t erroresImu = 0;
uint32_t atrasos = 0;      // muestras que empezaron mas de 2 ms tarde

// ---------------- Cinematica ----------------
float alphaMaxDeg(const Eje &e) {
  float k = min(e.rBrazo / e.rPlato, 1.0f);
  return asinf(k) * RAD_TO_DEG * 0.98f;   // margen para que exista el arcoseno
}

// Angulo del servo para un angulo del plato. Satura alpha si hace falta.
float thetaDeAlpha(const Eje &e, float &alpha) {
  float lim = alphaMaxDeg(e);
  alpha = constrain(alpha, -lim, lim);
  return asinf(sinf(alpha * DEG_TO_RAD) * e.rPlato / e.rBrazo) * RAD_TO_DEG;
}

// ---------------- Tarea de los servos ----------------
// En el core 3.x del ESP32, writeMicroseconds puede quedarse esperando hasta
// un periodo del PWM (20 ms). Con dos servos eso atrasaba cada muestra de
// 10 ms a ~40 ms. Por eso los servos se escriben en una tarea aparte en el
// nucleo 0, y el muestreo (nucleo 1) solo deja el pulso pedido en pulsoUs[].
volatile int pulsoUs[2] = {1500, 1500};

void tareaServos(void *) {
  int escrito[2] = {-1, -1};
  for (;;) {
    for (int i = 0; i < 2; i++) {
      int us = pulsoUs[i];
      if (us != escrito[i]) {
        ejes[i].servo.writeMicroseconds(us);
        escrito[i] = us;
      }
    }
    vTaskDelay(1);
  }
}

void escribirServo(Eje &e, float theta) {
  e.thetaCmd = theta;
  float us = e.centroUs + e.signoServo * US_PER_DEG * theta;
  pulsoUs[&e - ejes] = (int)constrain(us, (float)US_MIN, (float)US_MAX);
}

// Lleva el plato al angulo alpha y devuelve el alpha aplicado (saturado).
float ponerAlpha(Eje &e, float alpha) {
  float theta = thetaDeAlpha(e, alpha);
  escribirServo(e, theta);
  return alpha;
}

// ---------------- Potenciometro ----------------
// analogReadMilliVolts usa la calibracion de fabrica del ADC: es mas lineal
// que analogRead. Se promedian 8 lecturas para bajar el ruido del motor.
float leerPotMv(const Eje &e) {
  uint32_t suma = 0;
  for (int i = 0; i < 8; i++) {
    suma += analogReadMilliVolts(e.pinPot);
  }
  return suma / 8.0f;
}

// Angulo real del eje del servo [grados], en la misma escala que thetaCmd.
float leerPotTheta(const Eje &e) {
  if (!USAR_POT) {
    return NAN;
  }
  return -POT_CAL_DEG + (leerPotMv(e) - e.potMvA) * (2.0f * POT_CAL_DEG)
                        / (e.potMvB - e.potMvA);
}

// ---------------- IMU ----------------
void escribirRegistro(uint8_t reg, uint8_t valor) {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(reg);
  Wire.write(valor);
  Wire.endTransmission(true);
}

// acc: roll y pitch segun la gravedad [grados]; gyr: velocidad en x, y [grados/s].
bool leerIMU(float acc[2], float gyr[2]) {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x3B);
  if (Wire.endTransmission(false) != 0) {
    return false;
  }
  if (Wire.requestFrom((uint16_t)MPU_ADDR, (size_t)14) != 14) {
    return false;
  }

  // ax, ay, az, temperatura, gx, gy, gz
  int16_t r[7];
  for (int i = 0; i < 7; i++) {
    uint8_t alto = Wire.read();
    uint8_t bajo = Wire.read();
    r[i] = (int16_t)((alto << 8) | bajo);
  }

  float ax = r[0];
  float ay = r[1];
  float az = r[2];
  acc[0] = atan2f(ay, sqrtf(ax * ax + az * az)) * RAD_TO_DEG;
  acc[1] = atan2f(-ax, sqrtf(ay * ay + az * az)) * RAD_TO_DEG;
  gyr[0] = r[4] / GYRO_LSB;
  gyr[1] = r[5] / GYRO_LSB;
  return true;
}

// Indice del eje del IMU que corresponde al eje i del plato.
int ejeImu(int i) {
  return IMU_EJES_CRUZADOS ? 1 - i : i;
}

void actualizarIMU() {
  uint32_t ahora = micros();
  float dt = (ahora - ultimoImuUs) / 1000000.0f;
  ultimoImuUs = ahora;
  dt = min(dt, 0.05f);   // despues de una pausa larga, no integrar de golpe

  float acc[2];
  float gyr[2];
  if (!leerIMU(acc, gyr)) {
    erroresImu++;
    return;
  }

  for (int i = 0; i < 2; i++) {
    Eje &e = ejes[i];
    int k = ejeImu(i);
    e.gyro = gyr[k] - e.sesgoGyro;
    e.anguloCrudo = FILTRO * (e.anguloCrudo + e.gyro * dt) + (1.0f - FILTRO) * acc[k];
  }
}

float alphaImu(const Eje &e) {
  return e.signoImu * (e.anguloCrudo - e.offsetImu);
}

float gyroPlato(const Eje &e) {
  return e.signoImu * e.gyro;
}

// Plato quieto: mide el sesgo del giroscopio y arranca el filtro con el acelerometro.
void calibrarGyro() {
  float suma[2] = {0, 0};
  float acc[2];
  float gyr[2];
  int n = 0;

  for (int i = 0; i < 400; i++) {
    if (leerIMU(acc, gyr)) {
      suma[0] += gyr[0];
      suma[1] += gyr[1];
      n++;
    }
    delay(2);
  }

  if (n == 0) {
    Serial.println(F("# ERROR: el MPU6050 no responde. Revisar SDA=21, SCL=22, 3.3V y GND."));
    return;
  }

  for (int i = 0; i < 2; i++) {
    int k = ejeImu(i);
    ejes[i].sesgoGyro = suma[k] / n;
    ejes[i].anguloCrudo = acc[k];
  }
  ultimoImuUs = micros();
}

// ---------------- Tiempo ----------------
// Espera al siguiente instante de muestreo y actualiza el IMU.
void tick() {
  int32_t retraso = (int32_t)(micros() - proximoTick);
  if (retraso > 2000) {
    atrasos++;
  }
  if (retraso > (int32_t)TS_US) {
    proximoTick = micros();   // tras una pausa (volcado, etc.) no recuperar ticks
  }
  while ((int32_t)(micros() - proximoTick) < 0) {
  }
  proximoTick += TS_US;
  actualizarIMU();
}

void esperar(uint32_t ms) {
  for (uint32_t i = 0; i < ms * 1000UL / TS_US; i++) {
    tick();
  }
}

// Promedio de la salida cruda del filtro de cada eje durante ms.
void medirCrudo(float salida[2], uint32_t ms) {
  float suma[2] = {0, 0};
  uint32_t n = ms * 1000UL / TS_US;
  for (uint32_t i = 0; i < n; i++) {
    tick();
    suma[0] += ejes[0].anguloCrudo;
    suma[1] += ejes[1].anguloCrudo;
  }
  salida[0] = suma[0] / n;
  salida[1] = suma[1] / n;
}

void medirAlphas(float salida[2], uint32_t ms) {
  float crudo[2];
  medirCrudo(crudo, ms);
  for (int i = 0; i < 2; i++) {
    salida[i] = ejes[i].signoImu * (crudo[i] - ejes[i].offsetImu);
  }
}

// ---------------- Calibracion ----------------
// Para cada eje: mueve el centro +40 us para medir cuanto se inclina el plato
// (y revisar signos), luego corrige el centro hasta que el IMU marque ~0.
void nivelar() {
  const float PRUEBA_US = 40.0f;
  Serial.println(F("# NIVELANDO: no tocar el plato"));

  for (int i = 0; i < 2; i++) {
    Eje &e = ejes[i];
    float a0[2];
    float a1[2];

    ponerAlpha(ejes[0], 0);
    ponerAlpha(ejes[1], 0);
    esperar(800);
    medirAlphas(a0, 300);

    e.centroUs += PRUEBA_US;
    escribirServo(e, 0);
    esperar(800);
    medirAlphas(a1, 300);

    float propio = a1[i] - a0[i];
    float cruzado = a1[1 - i] - a0[1 - i];
    Serial.printf("# Eje %c: +%.0f us -> eje %c cambio %.2f grados, eje %c %.2f grados\n",
                  e.nombre, PRUEBA_US, e.nombre, propio, ejes[1 - i].nombre, cruzado);

    if (fabsf(propio) < 0.2f) {
      e.centroUs -= PRUEBA_US;
      escribirServo(e, 0);
      Serial.printf("# AVISO eje %c: el plato casi no se movio. Revisar servo, "
                    "alimentacion de 6 V y biela.\n", e.nombre);
      continue;
    }
    if (fabsf(cruzado) > fabsf(propio)) {
      Serial.println(F("# AVISO: se movio mas el otro eje. Cambiar IMU_EJES_CRUZADOS."));
    }
    // +us con signoServo = 1 es theta positivo, que debe dar alpha positivo.
    if ((propio > 0) != (e.signoServo > 0)) {
      Serial.printf("# AVISO eje %c: theta positivo inclina en negativo. Cambiar el "
                    "signoImu de este eje (o signoServo si el positivo debe ir al "
                    "otro lado).\n", e.nombre);
    }

    float relacion = fabsf(propio) / (PRUEBA_US / US_PER_DEG);
    Serial.printf("# Eje %c: alpha/theta medido = %.3f  (rBrazo/rPlato = %.3f)\n",
                  e.nombre, relacion, e.rBrazo / e.rPlato);

    // Corregir el centro con la pendiente medida (grados por us).
    float pendiente = propio / PRUEBA_US;
    float a = a1[i];
    for (int it = 0; it < 6 && fabsf(a) > 0.1f; it++) {
      e.centroUs -= a / pendiente;
      e.centroUs = constrain(e.centroUs, 1500.0f - CENTRO_MAX_US, 1500.0f + CENTRO_MAX_US);
      escribirServo(e, 0);
      esperar(800);
      float m[2];
      medirAlphas(m, 300);
      a = m[i];
    }
    Serial.printf("# Eje %c: centro = %.0f us, angulo = %.2f grados\n",
                  e.nombre, e.centroUs, a);
  }

  Serial.println(F("# Revisar con un nivel (o el celular) sobre el plato. Si esta bien, enviar G."));
}

// El plato esta nivelado ahora: lo que marque el IMU pasa a ser el cero.
void ceroImu() {
  float crudo[2];
  medirCrudo(crudo, 500);
  for (int i = 0; i < 2; i++) {
    ejes[i].offsetImu = crudo[i];
  }
  Serial.printf("# Cero del IMU: offsetX = %.2f, offsetY = %.2f grados\n", crudo[0], crudo[1]);
}

float promedioPot(const Eje &e, uint32_t ms) {
  float suma = 0;
  uint32_t n = ms * 1000UL / TS_US;
  for (uint32_t i = 0; i < n; i++) {
    tick();
    suma += leerPotMv(e);
  }
  return suma / n;
}

// Recorre el servo de -POT_CAL_DEG a +POT_CAL_DEG, mide el potenciometro en
// cada punto y ajusta una recta por minimos cuadrados: mV = a + b * theta.
void calibrarPot() {
  if (!USAR_POT) {
    Serial.println(F("# USAR_POT = false: no hay potenciometros que calibrar"));
    return;
  }

  for (int i = 0; i < 2; i++) {
    Eje &e = ejes[i];
    float th[POT_PUNTOS];
    float mv[POT_PUNTOS];

    Serial.printf("# Pot %c: theta_servo [grados] -> mV\n", e.nombre);
    for (int k = 0; k < POT_PUNTOS; k++) {
      th[k] = -POT_CAL_DEG + k * (2.0f * POT_CAL_DEG) / (POT_PUNTOS - 1);
      escribirServo(e, th[k]);
      esperar(k == 0 ? 1000 : 500);
      mv[k] = promedioPot(e, 200);
      Serial.printf("#   %6.1f -> %7.1f\n", th[k], mv[k]);
    }
    ponerAlpha(e, 0);

    float st = 0, sm = 0, stt = 0, stm = 0;
    float mvMin = mv[0], mvMax = mv[0];
    for (int k = 0; k < POT_PUNTOS; k++) {
      st += th[k];
      sm += mv[k];
      stt += th[k] * th[k];
      stm += th[k] * mv[k];
      mvMin = min(mvMin, mv[k]);
      mvMax = max(mvMax, mv[k]);
    }
    float b = (POT_PUNTOS * stm - st * sm) / (POT_PUNTOS * stt - st * st);   // mV por grado
    float a = (sm - b * st) / POT_PUNTOS;

    if (fabsf(b) < 3.0f) {
      Serial.printf("# AVISO pot %c: casi no cambia (%.1f mV/grado). Revisar el cable del "
                    "cursor y el GND comun. No se cambio la calibracion.\n", e.nombre, b);
      esperar(500);
      continue;
    }

    // Error de cada punto respecto a la recta, en grados.
    float errMax = 0;
    for (int k = 0; k < POT_PUNTOS; k++) {
      errMax = max(errMax, fabsf((mv[k] - a) / b - th[k]));
    }

    e.potMvA = a - b * POT_CAL_DEG;
    e.potMvB = a + b * POT_CAL_DEG;
    Serial.printf("# Pot %c: %.1f mV/grado, rango %.0f-%.0f mV, error maximo %.2f grados\n",
                  e.nombre, b, mvMin, mvMax, errMax);

    if (mvMax > 3000 || mvMin < 100) {
      Serial.printf("# AVISO pot %c: cerca del limite del ADC (0-3.1 V). Poner un divisor "
                    "de voltaje.\n", e.nombre);
    }
    if (errMax > 1.0f) {
      Serial.printf("# AVISO pot %c: los puntos no forman una recta (ruido o saturacion).\n",
                    e.nombre);
    }
    esperar(500);
  }

  Serial.println(F("# Si los pots estan bien, enviar G para guardar."));
}

void guardarCalibracion() {
  prefs.begin("plato", false);
  for (int i = 0; i < 2; i++) {
    Eje &e = ejes[i];
    String n(e.nombre);
    prefs.putFloat(("c" + n).c_str(), e.centroUs);
    prefs.putFloat(("pa" + n).c_str(), e.potMvA);
    prefs.putFloat(("pb" + n).c_str(), e.potMvB);
    prefs.putFloat(("o" + n).c_str(), e.offsetImu);
    prefs.putFloat(("kp" + n).c_str(), e.kp);
    prefs.putFloat(("ki" + n).c_str(), e.ki);
    prefs.putFloat(("kd" + n).c_str(), e.kd);
  }
  prefs.end();
  Serial.println(F("# Calibracion guardada"));
}

void cargarCalibracion() {
  prefs.begin("plato", true);
  for (int i = 0; i < 2; i++) {
    Eje &e = ejes[i];
    String n(e.nombre);
    e.centroUs = prefs.getFloat(("c" + n).c_str(), e.centroUs);
    e.potMvA = prefs.getFloat(("pa" + n).c_str(), e.potMvA);
    e.potMvB = prefs.getFloat(("pb" + n).c_str(), e.potMvB);
    e.offsetImu = prefs.getFloat(("o" + n).c_str(), e.offsetImu);
    e.kp = prefs.getFloat(("kp" + n).c_str(), e.kp);
    e.ki = prefs.getFloat(("ki" + n).c_str(), e.ki);
    e.kd = prefs.getFloat(("kd" + n).c_str(), e.kd);
  }
  prefs.end();
}

// ---------------- Mensajes ----------------
void mostrarAyuda() {
  Serial.println(F("# ? estado | N nivelar | TX,us / TY,us centro | Z cero IMU"));
  Serial.println(F("# C calibrar pots | G guardar | P,ax,ay mover"));
  Serial.println(F("# E,eje,amp escalones | W,eje,amp,freq seno   (eje: X, Y o A)"));
  Serial.println(F("# Lazo cerrado: K,eje,kp,ki,kd ganancias | R,eje,amp escalones | "
                   "S,eje,amp,freq seno"));
}

void mostrarEstado() {
  for (int i = 0; i < 2; i++) {
    Eje &e = ejes[i];
    Serial.printf("# Eje %c: centro %.0f us, offset IMU %.2f, pot %.0f/%.0f mV, "
                  "alpha max %.1f | alpha_imu %.2f, theta_cmd %.1f, theta_pot %.1f (%.0f mV)\n",
                  e.nombre, e.centroUs, e.offsetImu, e.potMvA, e.potMvB,
                  alphaMaxDeg(e), alphaImu(e), e.thetaCmd, leerPotTheta(e),
                  USAR_POT ? leerPotMv(e) : NAN);
    Serial.printf("#        PI: kp %.4f, ki %.3f, kd %.4f\n", e.kp, e.ki, e.kd);
  }
  Serial.printf("# Errores de lectura del IMU: %lu\n", (unsigned long)erroresImu);
}

// ---------------- Control ----------------
// PI (+ D con el giroscopio) del angulo del plato. Mismo algoritmo que
// simularPI() en disenar_control_plato.m. Devuelve alpha_cmd saturado; si la
// salida esta saturada no se integra (anti-windup).
float controlarEje(Eje &e, float ref) {
  float err = ref - alphaImu(e);
  float derivada = e.kd * gyroPlato(e);
  float uLibre = e.kp * err + e.integ + e.ki * TS_S * err - derivada;
  if (fabsf(uLibre) < ALPHA_SAT_LC || (err > 0) != (uLibre > 0)) {
    e.integ += e.ki * TS_S * err;
  }
  return constrain(e.kp * err + e.integ - derivada, -ALPHA_SAT_LC, ALPHA_SAT_LC);
}

// ---------------- Experimentos ----------------
// tipo: 'E' escalones, 'W' seno. En lazo cerrado se controlan los dos ejes:
// el eje del ensayo sigue la referencia y el otro se mantiene en 0.
float referencia(char tipo, float t, float amp, float freq) {
  if (tipo == 'E') {
    int k = min((int)(t / T_ESCALON_S), N_ESC - 1);
    return SEQ_ESC[k] * amp;
  }
  if (t < T_QUIETO_S || t >= T_QUIETO_S + T_SENO_S) {
    return 0;
  }
  return amp * sinf(2.0f * PI * freq * (t - T_QUIETO_S));
}

void experimento(char tipo, char eje, float amp, float freq, bool lazoCerrado) {
  bool usarX = (eje == 'X' || eje == 'A');
  bool usarY = (eje == 'Y' || eje == 'A');
  if (!usarX && !usarY) {
    Serial.println(F("# ERROR: eje debe ser X, Y o A"));
    return;
  }

  float duracion = (tipo == 'E') ? N_ESC * T_ESCALON_S : T_SENO_S + 2.0f * T_QUIETO_S;
  int n = min((int)(duracion * 1000000.0f / TS_US), MAX_MUESTRAS);

  float pico = (tipo == 'E') ? 2.0f * amp : amp;
  float limite = lazoCerrado ? ALPHA_SAT_LC
                             : min(alphaMaxDeg(ejes[0]), alphaMaxDeg(ejes[1]));
  if (pico > limite) {
    Serial.println(F("# AVISO: la referencia pasa el alpha maximo y se va a saturar"));
  }

  ponerAlpha(ejes[0], 0);
  ponerAlpha(ejes[1], 0);
  if (lazoCerrado) {
    // 1 s regulando en 0 para que la integral compense el error de nivelado.
    ejes[0].integ = 0;
    ejes[1].integ = 0;
    for (int i = 0; i < 100; i++) {
      tick();
      ponerAlpha(ejes[0], controlarEje(ejes[0], 0));
      ponerAlpha(ejes[1], controlarEje(ejes[1], 0));
    }
  } else {
    esperar(1000);
  }

  atrasos = 0;
  uint32_t t0 = 0;
  for (int i = 0; i < n; i++) {
    tick();
    if (i == 0) {
      t0 = micros();
    }
    float t = (micros() - t0) / 1000000.0f;
    float r = referencia(tipo, t, amp, freq);
    Muestra &m = buf[i];
    m.t_ms = t * 1000.0f;

    // Medir antes de mover: la respuesta aparece desde la muestra siguiente.
    m.axImu = alphaImu(ejes[0]);
    m.ayImu = alphaImu(ejes[1]);
    m.gx = gyroPlato(ejes[0]);
    m.gy = gyroPlato(ejes[1]);
    m.thxPot = leerPotTheta(ejes[0]);
    m.thyPot = leerPotTheta(ejes[1]);

    m.axRef = usarX ? r : 0;
    m.ayRef = usarY ? r : 0;
    if (lazoCerrado) {
      m.axCmd = ponerAlpha(ejes[0], controlarEje(ejes[0], m.axRef));
      m.ayCmd = ponerAlpha(ejes[1], controlarEje(ejes[1], m.ayRef));
    } else {
      m.axCmd = ponerAlpha(ejes[0], m.axRef);
      m.ayCmd = ponerAlpha(ejes[1], m.ayRef);
    }
    m.thxCmd = ejes[0].thetaCmd;
    m.thyCmd = ejes[1].thetaCmd;
  }

  float durReal = (micros() - t0) / 1000000.0f;
  float durEsperada = (n - 1) * (TS_US / 1000000.0f);
  ponerAlpha(ejes[0], 0);
  ponerAlpha(ejes[1], 0);

  Serial.printf("# INICIO tipo=%c eje=%c amp=%.2f freq=%.2f ts_ms=%lu lazo=%s\n",
                tipo, eje, amp, freq, (unsigned long)(TS_US / 1000),
                lazoCerrado ? "cerrado" : "abierto");
  if (lazoCerrado) {
    for (int i = 0; i < 2; i++) {
      Serial.printf("# PI %c: kp %.4f, ki %.3f, kd %.4f\n",
                    ejes[i].nombre, ejes[i].kp, ejes[i].ki, ejes[i].kd);
    }
  }
  Serial.println(F("t_ms,ax_cmd,ay_cmd,thx_cmd,thy_cmd,thx_pot,thy_pot,ax_imu,ay_imu,gx,gy,"
                   "ax_ref,ay_ref"));
  for (int i = 0; i < n; i++) {
    Muestra &m = buf[i];
    Serial.printf("%.2f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.2f,%.2f,%.3f,%.3f\n",
                  m.t_ms, m.axCmd, m.ayCmd, m.thxCmd, m.thyCmd,
                  m.thxPot, m.thyPot, m.axImu, m.ayImu, m.gx, m.gy, m.axRef, m.ayRef);
  }
  Serial.printf("# Errores de lectura del IMU: %lu\n", (unsigned long)erroresImu);
  Serial.printf("# Duracion real %.2f s (esperada %.2f s), muestras atrasadas: %lu de %d\n",
                durReal, durEsperada, (unsigned long)atrasos, n);
  if (durReal > 1.05f * durEsperada) {
    Serial.println(F("# AVISO: el muestreo fue mas lento que 10 ms por muestra"));
  }
  Serial.println(F("# FIN"));
}

// ---------------- Comandos ----------------
// Campo n (0 = comando) de una linea separada por comas.
String campo(const String &linea, int n) {
  int inicio = 0;
  for (int i = 0; i < n; i++) {
    inicio = linea.indexOf(',', inicio) + 1;
    if (inicio == 0) {
      return "";
    }
  }
  int fin = linea.indexOf(',', inicio);
  String s = linea.substring(inicio, fin < 0 ? linea.length() : fin);
  s.trim();
  return s;
}

void ejecutar(const String &linea) {
  String cmd = campo(linea, 0);

  if (cmd == "?") {
    mostrarEstado();
  } else if (cmd == "N") {
    nivelar();
  } else if (cmd == "TX" || cmd == "TY") {
    Eje &e = ejes[cmd == "TX" ? 0 : 1];
    e.centroUs = constrain(campo(linea, 1).toFloat(),
                           1500.0f - CENTRO_MAX_US, 1500.0f + CENTRO_MAX_US);
    ponerAlpha(e, 0);
    Serial.printf("# Centro %c = %.0f us\n", e.nombre, e.centroUs);
  } else if (cmd == "Z") {
    ceroImu();
  } else if (cmd == "C") {
    calibrarPot();
  } else if (cmd == "G") {
    guardarCalibracion();
  } else if (cmd == "P") {
    float ax = ponerAlpha(ejes[0], campo(linea, 1).toFloat());
    float ay = ponerAlpha(ejes[1], campo(linea, 2).toFloat());
    esperar(1000);
    Serial.printf("# Pedido X %.2f, Y %.2f | IMU X %.2f, Y %.2f | pot X %.1f, Y %.1f\n",
                  ax, ay, alphaImu(ejes[0]), alphaImu(ejes[1]),
                  leerPotTheta(ejes[0]), leerPotTheta(ejes[1]));
  } else if (cmd == "E" || cmd == "R") {
    experimento('E', campo(linea, 1).charAt(0), campo(linea, 2).toFloat(), 0, cmd == "R");
  } else if (cmd == "W" || cmd == "S") {
    experimento('W', campo(linea, 1).charAt(0), campo(linea, 2).toFloat(),
                campo(linea, 3).toFloat(), cmd == "S");
  } else if (cmd == "K") {
    char eje = campo(linea, 1).charAt(0);
    for (int i = 0; i < 2; i++) {
      Eje &e = ejes[i];
      if (eje != 'A' && eje != e.nombre) {
        continue;
      }
      e.kp = campo(linea, 2).toFloat();
      e.ki = campo(linea, 3).toFloat();
      e.kd = campo(linea, 4).toFloat();
      Serial.printf("# PI %c: kp %.4f, ki %.3f, kd %.4f  (G para guardar)\n",
                    e.nombre, e.kp, e.ki, e.kd);
    }
  } else {
    mostrarAyuda();
  }
}

// ---------------- Setup y loop ----------------
void setup() {
  Serial.begin(115200);
  Serial.setTimeout(100);
  Wire.begin();
  Wire.setClock(400000);

  escribirRegistro(0x6B, 0x00);   // despertar el MPU6050
  escribirRegistro(0x1A, 0x03);   // filtro pasa bajos ~44 Hz (vibracion de los servos)
  escribirRegistro(0x1B, 0x08);   // giroscopio +/-500 grados/s

  analogReadResolution(12);
  for (int i = 0; i < 2; i++) {
    analogSetPinAttenuation(ejes[i].pinPot, ADC_11db);   // rango 0 - ~3.1 V
  }
  cargarCalibracion();

  for (int i = 0; i < 2; i++) {
    ejes[i].servo.setPeriodHertz(50);
    ejes[i].servo.attach(ejes[i].pinServo, US_MIN, US_MAX);
    ponerAlpha(ejes[i], 0);
  }
  xTaskCreatePinnedToCore(tareaServos, "servos", 4096, NULL, 1, NULL, 0);

  delay(1000);   // que el plato llegue al centro antes de medir el sesgo
  Serial.println(F("# Calibrando giroscopio: plato quieto..."));
  calibrarGyro();

  proximoTick = micros() + TS_US;
  mostrarAyuda();
  mostrarEstado();
  Serial.println(F("# LISTO"));
}

void loop() {
  tick();   // el filtro del IMU corre siempre a 100 Hz

  if (Serial.available()) {
    String linea = Serial.readStringUntil('\n');
    linea.trim();
    linea.toUpperCase();
    if (linea.length() > 0) {
      ejecutar(linea);
    }
  }
}
