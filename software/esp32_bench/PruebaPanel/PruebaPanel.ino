// ========== PRUEBA DEL PANEL TACTIL RESISTIVO DE 4 HILOS (ESP32 DevKit) ==========
// Ver Project_ball/Electronica/plan_electronica.md, seccion 1.
//
// Dos modos (elegir con MODO):
//   DIRECTO  El ESP32 maneja los 4 terminales del panel con sus pines (sin 74HC4066).
//            Sirve para probar el panel y su conector antes de armar la placa.
//   SWITCH   El panel va a traves de la placa con el 74HC4066 (como en el myRIO).
//
// En los dos modos, poner R 100 kOhm de cada linea de lectura a GND (pull-down):
// sin pelota, la lectura cae a ~0 V y asi se detecta "sin toque".
//
// Monitor Serie a 115200. Imprime cada 20 ms:  vx_mV,vy_mV,tocado
// Para calibrar: anotar vx_mV y vy_mV con la pelota en las 4 esquinas del area util.

#include <Arduino.h>

#define DIRECTO 0
#define SWITCH  1
#define MODO    DIRECTO

// ---------------- Pines modo DIRECTO ----------------
// X+ e Y+ se usan como salida Y como entrada analogica: tienen que ser ADC1 con salida (32, 33).
const int XP = 32;   // X+
const int YP = 33;   // Y+
const int XM = 25;   // X-
const int YM = 26;   // Y-

// ---------------- Pines modo SWITCH ----------------
const int MEDIR_X = 25;   // -> ctrl-A y ctrl-B del 74HC4066
const int MEDIR_Y = 26;   // -> ctrl-C y ctrl-D
const int AI_X = 34;      // <- Y+ (a traves de 1 kOhm)
const int AI_Y = 35;      // <- X+ (a traves de 1 kOhm)

const uint32_t ESPERA_US = 1000;   // estabilizacion despues de cambiar de eje
const uint32_t PERIODO_MS = 20;
const int UMBRAL_MV = 50;          // por debajo: sin toque

void soltarTodo() {
  pinMode(XP, INPUT);
  pinMode(YP, INPUT);
  pinMode(XM, INPUT);
  pinMode(YM, INPUT);
}

int leerDirecto(bool ejeX) {
  soltarTodo();
  int alto = ejeX ? XP : YP, bajo = ejeX ? XM : YM, lectura = ejeX ? YP : XP;
  pinMode(alto, OUTPUT);
  digitalWrite(alto, HIGH);
  pinMode(bajo, OUTPUT);
  digitalWrite(bajo, LOW);
  delayMicroseconds(ESPERA_US);
  int mv = analogReadMilliVolts(lectura);
  soltarTodo();
  return mv;
}

int leerSwitch(bool ejeX) {
  digitalWrite(MEDIR_X, LOW);   // nunca las dos capas polarizadas a la vez
  digitalWrite(MEDIR_Y, LOW);
  digitalWrite(ejeX ? MEDIR_X : MEDIR_Y, HIGH);
  delayMicroseconds(ESPERA_US);
  int mv = analogReadMilliVolts(ejeX ? AI_X : AI_Y);
  digitalWrite(ejeX ? MEDIR_X : MEDIR_Y, LOW);
  return mv;
}

void setup() {
  Serial.begin(115200);
  analogReadResolution(12);
  analogSetAttenuation(ADC_11db);   // rango ~0-3.1 V
#if MODO == SWITCH
  pinMode(MEDIR_X, OUTPUT);
  pinMode(MEDIR_Y, OUTPUT);
  digitalWrite(MEDIR_X, LOW);
  digitalWrite(MEDIR_Y, LOW);
  Serial.println("# Modo SWITCH (74HC4066)");
#else
  soltarTodo();
  Serial.println("# Modo DIRECTO (ESP32 maneja el panel)");
#endif
  Serial.println("vx_mV,vy_mV,tocado");
}

void loop() {
  static uint32_t t_prev = 0;
  if (millis() - t_prev < PERIODO_MS) return;
  t_prev = millis();

#if MODO == SWITCH
  int vx = leerSwitch(true);
  int vy = leerSwitch(false);
#else
  int vx = leerDirecto(true);
  int vy = leerDirecto(false);
#endif
  bool tocado = vx > UMBRAL_MV && vy > UMBRAL_MV;

  Serial.print(vx);
  Serial.print(',');
  Serial.print(vy);
  Serial.print(',');
  Serial.println(tocado ? 1 : 0);
}
