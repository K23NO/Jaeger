// ========== ENSAYO DE TRAYECTORIA PARA IDENTIFICAR LA PLANTA ==========
// Modo T (trayectoria):
//   reposo 0.5 s -> avanzar 3 s -> girar 2 s -> detenido 1 s
// Modo A (adelante) / B (atras), las dos ruedas iguales, sin giro:
//   reposo 0.5 s -> recto 3 s -> detenido 1 s
// Modo G (giro en su propio eje, ruedas opuestas):
//   reposo 0.5 s -> girar 3 s -> detenido 1 s
// Cada 20 ms imprime una linea CSV por el puerto serie:
//   t_ms,etapa,pwmD,pwmI,pulsosD,pulsosI,wD,wI,v,w,x,y,theta_deg
//
// Comandos (Monitor Serie a 115200, fin de linea "Nueva linea"):
//   S              iniciar con los valores actuales
//   S,150          iniciar con PWM 150
//   S,150,I        PWM 150, giro a la izquierda (D = derecha)
//   S,150,I,M      ... girando sobre el punto medio del eje
//                  (M = punto medio, R = sobre una rueda fija)
//   S,150,D,R,B    ... modo B: solo hacia atras, sin giro
//                  (T = trayectoria, A = adelante, B = atras,
//                   G = giro en su eje hacia el lado D o I)
//
// Para guardar el CSV en la PC: python capturar_planta.py

#include <math.h>

// ========== MOTOR DERECHO ==========
const byte PWM_D = 9;
const byte DIR_D = 7;
const byte ENC_D_A = 2;
const byte ENC_D_B = 4;

// ========== MOTOR IZQUIERDO ==========
const byte PWM_I = 10;
const byte DIR_I = 8;
const byte ENC_I_A = 3;
const byte ENC_I_B = 5;

// Direccion de avance de cada motor.
// El izquierdo esta montado en espejo: avanza con DIR en HIGH.
const byte ADELANTE_D = LOW;
const byte ADELANTE_I = HIGH;

// Si los pulsos salen negativos al avanzar,
// cambiar el signo correspondiente a -1.
const int SIGNO_D = 1;
const int SIGNO_I = 1;

// ========== MEDIDAS ==========
const float RADIO = 0.045;       // 4.5 cm
const float SEPARACION = 0.33;   // 33 cm entre ruedas motrices
const float PULSOS_VUELTA = 1450.0;

// ========== ENSAYO ==========
const unsigned long TS_US = 20000UL;   // Periodo de muestreo: 20 ms

// Fin de cada etapa en ms desde el inicio.
const unsigned long FIN_REPOSO = 500UL;
const unsigned long FIN_AVANCE = FIN_REPOSO + 3000UL;
const unsigned long FIN_GIRO = FIN_AVANCE + 2000UL;
const unsigned long T_DETENIDO = 1000UL;

// AVANCE es el tramo recto (hacia atras en el modo B).
enum Etapa { REPOSO, AVANCE, GIRO, DETENIDO, TERMINADO };

int pwm = 120;
char sentidoGiro = 'D';   // D = derecha, I = izquierda
char tipoGiro = 'R';      // R = sobre una rueda fija, M = punto medio
char modo = 'T';          // T = trayectoria, A = adelante, B = atras, G = giro

// ========== ENCODERS ==========
volatile long pulsosD = 0;
volatile long pulsosI = 0;

long anterioresD = 0;
long anterioresI = 0;

// ========== POSICION ==========
float x = 0.0;
float y = 0.0;
float angulo = 0.0;  // Radianes

// Declaraciones de funciones.
void leerDerecho();
void leerIzquierdo();
void moverMotores(int pwmD, int pwmI);
void detener();
void mostrarAyuda();
void leerComando(String linea);
Etapa etapaEn(unsigned long t);
void aplicarEtapa(Etapa etapa, int &pwmD, int &pwmI);
void ensayo();
void muestrear(unsigned long t, Etapa etapa, int pwmD, int pwmI,
               float dt);

// ========== CONFIGURACION ==========
void setup() {
  pinMode(PWM_D, OUTPUT);
  pinMode(DIR_D, OUTPUT);
  pinMode(PWM_I, OUTPUT);
  pinMode(DIR_I, OUTPUT);

  detener();

  pinMode(ENC_D_A, INPUT_PULLUP);
  pinMode(ENC_D_B, INPUT_PULLUP);
  pinMode(ENC_I_A, INPUT_PULLUP);
  pinMode(ENC_I_B, INPUT_PULLUP);

  Serial.begin(115200);

  attachInterrupt(
    digitalPinToInterrupt(ENC_D_A), leerDerecho, RISING
  );

  attachInterrupt(
    digitalPinToInterrupt(ENC_I_A), leerIzquierdo, RISING
  );

  mostrarAyuda();
  Serial.println(F("# LISTO"));
}

// ========== ESPERAR COMANDO ==========
void loop() {
  if (!Serial.available()) {
    return;
  }

  String linea = Serial.readStringUntil('\n');
  linea.trim();

  if (linea.length() == 0) {
    return;
  }

  if (toupper(linea.charAt(0)) != 'S') {
    mostrarAyuda();
    return;
  }

  leerComando(linea);
  ensayo();
}

void mostrarAyuda() {
  Serial.println(F("# ENSAYO: reposo 0.5 s, avanzar 3 s, girar 2 s, detenido 1 s"));
  Serial.println(F("# Enviar S  o  S,<pwm>,<D|I>,<R|M>,<T|A|B|G>   ej: S,150,I,M,T"));
}

// Lee los campos opcionales de "S,<pwm>,<giro>,<tipo>,<modo>".
void leerComando(String linea) {
  int coma1 = linea.indexOf(',');
  if (coma1 < 0) {
    return;
  }
  pwm = constrain(linea.substring(coma1 + 1).toInt(), 0, 255);

  int coma2 = linea.indexOf(',', coma1 + 1);
  if (coma2 < 0) {
    return;
  }
  char giro = toupper(linea.charAt(coma2 + 1));
  if (giro == 'D' || giro == 'I') {
    sentidoGiro = giro;
  }

  int coma3 = linea.indexOf(',', coma2 + 1);
  if (coma3 < 0) {
    return;
  }
  char tipo = toupper(linea.charAt(coma3 + 1));
  if (tipo == 'R' || tipo == 'M') {
    tipoGiro = tipo;
  }

  int coma4 = linea.indexOf(',', coma3 + 1);
  if (coma4 < 0) {
    return;
  }
  char m = toupper(linea.charAt(coma4 + 1));
  if (m == 'T' || m == 'A' || m == 'B' || m == 'G') {
    modo = m;
  }
}

// ========== MOTORES ==========
// PWM con signo: positivo = adelante, negativo = atras.
void moverMotores(int pwmD, int pwmI) {
  digitalWrite(DIR_D, pwmD >= 0 ? ADELANTE_D : !ADELANTE_D);
  digitalWrite(DIR_I, pwmI >= 0 ? ADELANTE_I : !ADELANTE_I);
  analogWrite(PWM_D, abs(pwmD));
  analogWrite(PWM_I, abs(pwmI));
}

void detener() {
  analogWrite(PWM_D, 0);
  analogWrite(PWM_I, 0);
}

// ========== LECTURA DE ENCODERS ==========
void leerDerecho() {
  if (digitalRead(ENC_D_B) == HIGH) {
    pulsosD += SIGNO_D;
  } else {
    pulsosD -= SIGNO_D;
  }
}

void leerIzquierdo() {
  if (digitalRead(ENC_I_B) == HIGH) {
    pulsosI += SIGNO_I;
  } else {
    pulsosI -= SIGNO_I;
  }
}

// ========== ETAPAS DEL ENSAYO ==========
Etapa etapaEn(unsigned long t) {
  if (t < FIN_REPOSO) return REPOSO;
  // En el modo G se gira durante el tiempo del tramo recto.
  if (t < FIN_AVANCE) return (modo == 'G') ? GIRO : AVANCE;

  // En los modos A, B y G no hay un giro despues del tramo recto.
  unsigned long finGiro = (modo == 'T') ? FIN_GIRO : FIN_AVANCE;
  if (t < finGiro) return GIRO;
  if (t < finGiro + T_DETENIDO) return DETENIDO;
  return TERMINADO;
}

void aplicarEtapa(Etapa etapa, int &pwmD, int &pwmI) {
  pwmD = 0;
  pwmI = 0;

  if (etapa == AVANCE) {
    int signo = (modo == 'B') ? -1 : 1;
    pwmD = signo * pwm;
    pwmI = signo * pwm;
  } else if (etapa == GIRO) {
    // Giro a la derecha: la rueda izquierda avanza y la derecha
    // se detiene (R) o retrocede (M). A la izquierda, al reves.
    // El modo G siempre gira sobre el punto medio.
    int atras = (tipoGiro == 'M' || modo == 'G') ? -pwm : 0;
    if (sentidoGiro == 'D') {
      pwmI = pwm;
      pwmD = atras;
    } else {
      pwmD = pwm;
      pwmI = atras;
    }
  }

  moverMotores(pwmD, pwmI);
}

void ensayo() {
  noInterrupts();
  pulsosD = 0;
  pulsosI = 0;
  interrupts();

  anterioresD = 0;
  anterioresI = 0;
  x = 0.0;
  y = 0.0;
  angulo = 0.0;

  Serial.print(F("# INICIO modo="));
  Serial.print(modo);
  Serial.print(F(" pwm="));
  Serial.print(pwm);
  Serial.print(F(" giro="));
  Serial.print(sentidoGiro);
  Serial.print(F(" tipo="));
  Serial.print(tipoGiro);
  Serial.print(F(" ts_ms="));
  Serial.println(TS_US / 1000);
  Serial.println(F("t_ms,etapa,pwmD,pwmI,pulsosD,pulsosI,"
                   "wD,wI,v,w,x,y,theta_deg"));

  Etapa etapa = REPOSO;
  int pwmD = 0;
  int pwmI = 0;
  aplicarEtapa(etapa, pwmD, pwmI);

  unsigned long inicio = micros();
  unsigned long proximo = inicio + TS_US;
  unsigned long anterior = inicio;

  while (true) {
    unsigned long ahora = micros();

    // Esperar al siguiente instante de muestreo.
    if ((long)(ahora - proximo) < 0) {
      continue;
    }
    proximo += TS_US;

    unsigned long t = (ahora - inicio) / 1000UL;
    Etapa nueva = etapaEn(t);

    if (nueva == TERMINADO) {
      break;
    }

    float dt = (ahora - anterior) / 1000000.0;
    anterior = ahora;

    // Muestrear con el PWM que estuvo aplicado en el intervalo
    // anterior y luego cambiar de etapa si corresponde.
    muestrear(t, etapa, pwmD, pwmI, dt);

    if (nueva != etapa) {
      etapa = nueva;
      aplicarEtapa(etapa, pwmD, pwmI);
    }
  }

  detener();

  Serial.print(F("# POSICION FINAL x="));
  Serial.print(x, 4);
  Serial.print(F(" m, y="));
  Serial.print(y, 4);
  Serial.print(F(" m, theta="));
  Serial.print(angulo * 180.0 / PI, 2);
  Serial.println(F(" grados"));
  Serial.println(F("# FIN"));
}

// ========== CALCULAR E IMPRIMIR UNA MUESTRA ==========
void muestrear(unsigned long t, Etapa etapa, int pwmD, int pwmI,
               float dt) {
  long cuentasD;
  long cuentasI;

  // Copiar ambos contadores sin interrupciones.
  noInterrupts();
  cuentasD = pulsosD;
  cuentasI = pulsosI;
  interrupts();

  // Pulsos desde la muestra anterior.
  long cambioD = cuentasD - anterioresD;
  long cambioI = cuentasI - anterioresI;

  anterioresD = cuentasD;
  anterioresI = cuentasI;

  // Giro de cada rueda en radianes y su velocidad.
  float giroD = cambioD * 2.0 * PI / PULSOS_VUELTA;
  float giroI = cambioI * 2.0 * PI / PULSOS_VUELTA;
  float wD = giroD / dt;
  float wI = giroI / dt;

  // Distancia de cada rueda en metros.
  float distanciaD = giroD * RADIO;
  float distanciaI = giroI * RADIO;

  // Desplazamiento y giro del centro del robot.
  float distancia = (distanciaD + distanciaI) / 2.0;
  float cambioAngulo = (distanciaD - distanciaI) / SEPARACION;

  // Actualizar posicion.
  float anguloMedio = angulo + cambioAngulo / 2.0;

  x += distancia * cos(anguloMedio);
  y += distancia * sin(anguloMedio);
  angulo += cambioAngulo;

  // Una linea CSV.
  Serial.print(t);
  Serial.print(',');
  Serial.print((int)etapa);
  Serial.print(',');
  Serial.print(pwmD);
  Serial.print(',');
  Serial.print(pwmI);
  Serial.print(',');
  Serial.print(cuentasD);
  Serial.print(',');
  Serial.print(cuentasI);
  Serial.print(',');
  Serial.print(wD, 3);
  Serial.print(',');
  Serial.print(wI, 3);
  Serial.print(',');
  Serial.print(distancia / dt, 4);
  Serial.print(',');
  Serial.print(cambioAngulo / dt, 4);
  Serial.print(',');
  Serial.print(x, 4);
  Serial.print(',');
  Serial.print(y, 4);
  Serial.print(',');
  Serial.println(angulo * 180.0 / PI, 2);
}
