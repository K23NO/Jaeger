// ========== PRUEBA DE ENCODERS DE LA BASE MOVIL ==========
// Abrir el Monitor Serie a 115200 baudios y enviar una letra:
//   m  Monitor manual: girar las ruedas a mano y ver los pulsos
//      (cualquier tecla para salir)
//   0  Poner los contadores en cero
//   d  Motor derecho adelante 2 s
//   i  Motor izquierdo adelante 2 s
//   a  Ambos motores adelante 2 s
//   r  Ambos motores atras 2 s
//   +  Subir PWM en 20
//   -  Bajar PWM en 20
//
// Los datos de las pruebas con motor salen en CSV
// (t_ms,pulsosD,pulsosI,rpmD,rpmI) para copiarlos a Excel.

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
const float RADIO = 0.045;         // 4.5 cm
const float PULSOS_VUELTA = 1450.0;

// ========== PRUEBA ==========
const unsigned long T_PRUEBA = 2000UL;   // Duracion con motor encendido
const unsigned long T_MUESTRA = 100UL;   // Periodo de impresion
const unsigned long T_FRENADO = 500UL;   // Espera despues de apagar

int pwm = 120;

// ========== ENCODERS ==========
volatile long pulsosD = 0;
volatile long pulsosI = 0;

// Declaraciones de funciones.
void leerDerecho();
void leerIzquierdo();
void leerContadores(long &cuentasD, long &cuentasI);
void ponerEnCero();
void vaciarEntrada();
void detener();
void mostrarMenu();
void monitorManual();
void probarMotores(bool usarD, bool usarI, bool adelante);
void revisarEncoder(const __FlashStringHelper *nombre, long cuentas,
                    bool usado, bool adelante);

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

  mostrarMenu();
}

// ========== MENU ==========
void loop() {
  if (!Serial.available()) {
    return;
  }

  char c = Serial.read();

  switch (c) {
    case 'm': monitorManual(); break;
    case '0':
      ponerEnCero();
      Serial.println(F("Contadores en cero"));
      break;
    case 'd': probarMotores(true, false, true); break;
    case 'i': probarMotores(false, true, true); break;
    case 'a': probarMotores(true, true, true); break;
    case 'r': probarMotores(true, true, false); break;
    case '+':
      pwm = min(pwm + 20, 255);
      Serial.print(F("PWM = "));
      Serial.println(pwm);
      break;
    case '-':
      pwm = max(pwm - 20, 0);
      Serial.print(F("PWM = "));
      Serial.println(pwm);
      break;
    case '\n':
    case '\r':
      break;
    default:
      mostrarMenu();
  }
}

void mostrarMenu() {
  Serial.println(F("================================"));
  Serial.println(F("PRUEBA DE ENCODERS"));
  Serial.println(F("  m  monitor manual (girar ruedas a mano)"));
  Serial.println(F("  0  contadores en cero"));
  Serial.println(F("  d  motor derecho adelante 2 s"));
  Serial.println(F("  i  motor izquierdo adelante 2 s"));
  Serial.println(F("  a  ambos adelante 2 s"));
  Serial.println(F("  r  ambos atras 2 s"));
  Serial.println(F("  + / -  subir / bajar PWM"));
  Serial.print(F("PWM actual = "));
  Serial.println(pwm);
  Serial.println(F("================================"));
}

// ========== DETENER MOTORES ==========
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

// Copiar ambos contadores sin interrupciones.
void leerContadores(long &cuentasD, long &cuentasI) {
  noInterrupts();
  cuentasD = pulsosD;
  cuentasI = pulsosI;
  interrupts();
}

void ponerEnCero() {
  noInterrupts();
  pulsosD = 0;
  pulsosI = 0;
  interrupts();
}

// Descarta lo que quede en el buffer (por ejemplo el '\n'
// que manda el Monitor Serie despues de la letra).
void vaciarEntrada() {
  delay(50);
  while (Serial.available()) {
    Serial.read();
  }
}

// ========== PRUEBA 1: GIRAR A MANO ==========
// Ademas de los pulsos por interrupcion, muestra el nivel de los
// pines A y B y cuenta los cambios del canal A leyendo el pin en
// el lazo. Asi se distingue si falla la senal o la interrupcion.
void monitorManual() {
  detener();
  ponerEnCero();
  vaciarEntrada();

  Serial.println(F("MONITOR: gira cada rueda a mano."));
  Serial.println(F("Envia cualquier tecla para salir."));
  Serial.println(F("pulsosD\tvueltasD\tpulsosI\tvueltasI"
                   "\tAD BD AI BI\tcambiosAD\tcambiosAI"));

  byte anteriorAD = digitalRead(ENC_D_A);
  byte anteriorAI = digitalRead(ENC_I_A);
  long cambiosAD = 0;
  long cambiosAI = 0;
  unsigned long ultimaLectura = millis();

  while (!Serial.available()) {
    byte aD = digitalRead(ENC_D_A);
    byte aI = digitalRead(ENC_I_A);

    if (aD != anteriorAD) {
      cambiosAD++;
      anteriorAD = aD;
    }
    if (aI != anteriorAI) {
      cambiosAI++;
      anteriorAI = aI;
    }

    if (millis() - ultimaLectura < 200UL) {
      continue;
    }
    ultimaLectura = millis();

    long cuentasD;
    long cuentasI;
    leerContadores(cuentasD, cuentasI);

    Serial.print(cuentasD);
    Serial.print('\t');
    Serial.print(cuentasD / PULSOS_VUELTA, 3);
    Serial.print('\t');
    Serial.print(cuentasI);
    Serial.print('\t');
    Serial.print(cuentasI / PULSOS_VUELTA, 3);
    Serial.print('\t');
    Serial.print(aD);
    Serial.print(F("  "));
    Serial.print(digitalRead(ENC_D_B));
    Serial.print(F("  "));
    Serial.print(aI);
    Serial.print(F("  "));
    Serial.print(digitalRead(ENC_I_B));
    Serial.print('\t');
    Serial.print(cambiosAD);
    Serial.print('\t');
    Serial.println(cambiosAI);
  }

  vaciarEntrada();
  Serial.println(F("Fin del monitor"));
}

// ========== PRUEBA 2: CON MOTOR ==========
void probarMotores(bool usarD, bool usarI, bool adelante) {
  vaciarEntrada();
  ponerEnCero();

  digitalWrite(DIR_D, adelante ? ADELANTE_D : !ADELANTE_D);
  digitalWrite(DIR_I, adelante ? ADELANTE_I : !ADELANTE_I);

  Serial.print(F("# PRUEBA: "));
  if (usarD && usarI) {
    Serial.print(F("AMBOS"));
  } else if (usarD) {
    Serial.print(F("DERECHO"));
  } else {
    Serial.print(F("IZQUIERDO"));
  }
  Serial.print(adelante ? F(" ADELANTE") : F(" ATRAS"));
  Serial.print(F(", PWM = "));
  Serial.println(pwm);
  Serial.println(F("t_ms,pulsosD,pulsosI,rpmD,rpmI"));

  long anteriorD = 0;
  long anteriorI = 0;
  long cuentasD = 0;
  long cuentasI = 0;

  unsigned long comienzo = millis();
  unsigned long ultimaLectura = comienzo;

  analogWrite(PWM_D, usarD ? pwm : 0);
  analogWrite(PWM_I, usarI ? pwm : 0);

  while (millis() - comienzo < T_PRUEBA) {
    unsigned long ahora = millis();

    if (ahora - ultimaLectura >= T_MUESTRA) {
      leerContadores(cuentasD, cuentasI);

      // Velocidad de cada rueda en el ultimo intervalo.
      float dt = (ahora - ultimaLectura) / 1000.0;
      float rpmD = (cuentasD - anteriorD) / PULSOS_VUELTA / dt * 60.0;
      float rpmI = (cuentasI - anteriorI) / PULSOS_VUELTA / dt * 60.0;

      Serial.print(ahora - comienzo);
      Serial.print(',');
      Serial.print(cuentasD);
      Serial.print(',');
      Serial.print(cuentasI);
      Serial.print(',');
      Serial.print(rpmD, 1);
      Serial.print(',');
      Serial.println(rpmI, 1);

      anteriorD = cuentasD;
      anteriorI = cuentasI;
      ultimaLectura = ahora;
    }
  }

  // Pulsos al apagar el motor y despues de que se detiene.
  long finD;
  long finI;
  leerContadores(finD, finI);
  detener();
  delay(T_FRENADO);
  leerContadores(cuentasD, cuentasI);

  float segundos = T_PRUEBA / 1000.0;

  Serial.println(F("# RESUMEN"));
  Serial.print(F("# Derecho:   "));
  Serial.print(cuentasD);
  Serial.print(F(" pulsos, "));
  Serial.print(cuentasD / PULSOS_VUELTA, 3);
  Serial.print(F(" vueltas, "));
  Serial.print(cuentasD / PULSOS_VUELTA * 2.0 * PI * RADIO, 3);
  Serial.print(F(" m, RPM medio "));
  Serial.print(finD / PULSOS_VUELTA / segundos * 60.0, 1);
  Serial.print(F(", inercia "));
  Serial.print(cuentasD - finD);
  Serial.println(F(" pulsos"));

  Serial.print(F("# Izquierdo: "));
  Serial.print(cuentasI);
  Serial.print(F(" pulsos, "));
  Serial.print(cuentasI / PULSOS_VUELTA, 3);
  Serial.print(F(" vueltas, "));
  Serial.print(cuentasI / PULSOS_VUELTA * 2.0 * PI * RADIO, 3);
  Serial.print(F(" m, RPM medio "));
  Serial.print(finI / PULSOS_VUELTA / segundos * 60.0, 1);
  Serial.print(F(", inercia "));
  Serial.print(cuentasI - finI);
  Serial.println(F(" pulsos"));

  revisarEncoder(F("DERECHO"), cuentasD, usarD, adelante);
  revisarEncoder(F("IZQUIERDO"), cuentasI, usarI, adelante);

  if (usarD && usarI && cuentasD != 0 && cuentasI != 0) {
    float diferencia = 100.0 * (abs(cuentasD) - abs(cuentasI))
                       / ((abs(cuentasD) + abs(cuentasI)) / 2.0);
    Serial.print(F("# Diferencia derecho - izquierdo: "));
    Serial.print(diferencia, 1);
    Serial.println(F(" %"));
  }

  Serial.println(F("# FIN DE LA PRUEBA"));
}

// Avisos automaticos sobre lo que puede estar mal.
void revisarEncoder(const __FlashStringHelper *nombre, long cuentas,
                    bool usado, bool adelante) {
  if (usado) {
    if (cuentas == 0) {
      Serial.print(F("# ERROR "));
      Serial.print(nombre);
      Serial.println(F(": 0 pulsos. Revisar canal A, 5V y GND del encoder."));
    } else if ((cuentas > 0) != adelante) {
      Serial.print(F("# AVISO "));
      Serial.print(nombre);
      Serial.println(F(": signo invertido. Si la rueda giro en el sentido"
                       " pedido, cambiar su SIGNO; si no, cambiar su ADELANTE."));
    } else {
      Serial.print(F("# OK "));
      Serial.println(nombre);
    }
  } else if (abs(cuentas) > 20) {
    Serial.print(F("# AVISO "));
    Serial.print(nombre);
    Serial.println(F(": cuenta sin que su motor gire. Cables D/I cruzados"
                     " o ruido."));
  }
}
