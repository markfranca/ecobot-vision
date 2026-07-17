#include <ESP32Servo.h>

const int BASE_SERVO_PIN = 25;
const int ARM_SERVO_PIN = 26;
const int CLAW_SERVO_PIN = 27;
const int TEST_BUTTON_PIN = 33;

const int SERVO_FREQUENCY_HZ = 50;
const int SERVO_MIN_PULSE_US = 500;
const int SERVO_MAX_PULSE_US = 2400;
const unsigned long BUTTON_DEBOUNCE_MS = 50;

// Altere para true para executar uma sequencia automaticamente ao ligar.
const bool RUN_TEST_ON_STARTUP = false;

const int BASE_HOME_ANGLE = 170;
const int BASE_TURN_ANGLE = 10;
const int ARM_HOME_ANGLE = 45;
const int ARM_RAISED_ANGLE = 110;
const int CLAW_HOME_ANGLE = 10;
const int CLAW_OPEN_ANGLE = 50;

const unsigned long ACTION_INTERVAL_MS = 500;

Servo baseServo;
Servo armServo;
Servo clawServo;

bool sequenceRunning = false;
int lastButtonReading = HIGH;
int stableButtonState = HIGH;
unsigned long lastButtonChangeMs = 0;

void waitForNextAction() {
  delay(ACTION_INTERVAL_MS);
}

void moveServo(Servo &servo, int servoPin, int targetAngle) {
  if (!servo.attached()) {
    servo.setPeriodHertz(SERVO_FREQUENCY_HZ);
    servo.attach(servoPin, SERVO_MIN_PULSE_US, SERVO_MAX_PULSE_US);
  }

  servo.write(targetAngle);
  waitForNextAction();
}

void discardPendingCommands() {
  while (Serial.available() > 0) {
    Serial.read();
  }
}

void runServoSequence() {
  sequenceRunning = true;
  Serial.println("BUSY");

  // Mesma sequencia validada em firmware/teste/teste.ino.
  // Garra: -80 graus.
  moveServo(clawServo, CLAW_SERVO_PIN, CLAW_OPEN_ANGLE);

  // Braco: +80 graus.
  moveServo(armServo, ARM_SERVO_PIN, ARM_HOME_ANGLE);

  // Garra: +80 graus.
  moveServo(clawServo, CLAW_SERVO_PIN, CLAW_HOME_ANGLE);

  // Braco: -80 graus.
  moveServo(armServo, ARM_SERVO_PIN, ARM_RAISED_ANGLE);

  // Base: giro de 180 graus.
  moveServo(baseServo, BASE_SERVO_PIN, BASE_TURN_ANGLE);

  // Braco: +90 graus.
  moveServo(armServo, ARM_SERVO_PIN, ARM_HOME_ANGLE);

  // Garra: -90 graus.
  moveServo(clawServo, CLAW_SERVO_PIN, CLAW_OPEN_ANGLE);

  // Braco: -90 graus.
  moveServo(armServo, ARM_SERVO_PIN, ARM_RAISED_ANGLE);

  // Garra: +90 graus.
  moveServo(clawServo, CLAW_SERVO_PIN, CLAW_HOME_ANGLE);

  // Base: segundo giro de 180 graus, retornando ao inicio.
  moveServo(baseServo, BASE_SERVO_PIN, BASE_HOME_ANGLE);

  // Nao executa novamente comandos que chegaram durante a sequencia.
  discardPendingCommands();
  sequenceRunning = false;
  Serial.println("OK SERVO");
}

void checkTestButton() {
  int buttonReading = digitalRead(TEST_BUTTON_PIN);

  if (buttonReading != lastButtonReading) {
    lastButtonChangeMs = millis();
    lastButtonReading = buttonReading;
  }

  if (millis() - lastButtonChangeMs < BUTTON_DEBOUNCE_MS) {
    return;
  }

  if (buttonReading == stableButtonState) {
    return;
  }

  stableButtonState = buttonReading;

  // INPUT_PULLUP: o botao pressionado conecta o GPIO ao GND.
  if (stableButtonState == LOW) {
    runServoSequence();
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(TEST_BUTTON_PIN, INPUT_PULLUP);

  // Reserva tres temporizadores PWM independentes do ESP32.
  ESP32PWM::allocateTimer(0);
  ESP32PWM::allocateTimer(1);
  ESP32PWM::allocateTimer(2);

  // Os servos so recebem PWM quando a visao enviar o comando SERVO.
  Serial.println("READY");

  if (RUN_TEST_ON_STARTUP) {
    delay(1000);
    runServoSequence();
  }
}

void loop() {
  if (sequenceRunning) {
    return;
  }

  checkTestButton();

  if (!Serial.available()) {
    return;
  }

  String command = Serial.readStringUntil('\n');
  command.trim();
  command.toUpperCase();

  // SERVO e o comando enviado pelos scripts Python do projeto.
  // PICK e OPEN continuam aceitos para compatibilidade.
  if (command == "SERVO" || command == "PICK" || command == "OPEN") {
    runServoSequence();
  } else {
    Serial.println("ERR");
  }
}
