#include <ESP32Servo.h>

const int BASE_SERVO_PIN = 25;
const int ARM_SERVO_PIN = 26;
const int CLAW_SERVO_PIN = 27;

const int SERVO_FREQUENCY_HZ = 50;
const int SERVO_MIN_PULSE_US = 500;
const int SERVO_MAX_PULSE_US = 2400;

const int BASE_HOME_ANGLE = 180;
const int BASE_TURN_ANGLE = 0;
const int ARM_HOME_ANGLE = 0;
const int ARM_RAISED_ANGLE = 70;
const int CLAW_HOME_ANGLE = 0;
const int CLAW_OPEN_ANGLE = 80;

const unsigned long START_DELAY_MS = 3000;
const unsigned long ACTION_INTERVAL_MS = 500;

Servo baseServo;
Servo armServo;
Servo clawServo;

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

void runServoSequence() {
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
}

void setup() {
  ESP32PWM::allocateTimer(0);
  ESP32PWM::allocateTimer(1);
  ESP32PWM::allocateTimer(2);

  // Nenhum servo recebe PWM antes de sua primeira acao na sequencia.
  delay(START_DELAY_MS);
  runServoSequence();
}

void loop() {
  // Vazio de proposito: a sequencia deve executar somente uma vez.
}
