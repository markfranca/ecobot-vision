#include <Servo.h>

const int SERVO_PIN = 9;
const int HOME_ANGLE = 0;
const int PICK_ANGLE = 90;
const unsigned long HOLD_MS = 1000;

Servo clawServo;

void moveAndReturn(int angle) {
  angle = constrain(angle, 0, 180);
  clawServo.write(angle);
  delay(HOLD_MS);
  clawServo.write(HOME_ANGLE);
  delay(300);
}

void setup() {
  Serial.begin(115200);
  clawServo.attach(SERVO_PIN);
  clawServo.write(HOME_ANGLE);
  Serial.println("READY");
}

void loop() {
  if (!Serial.available()) {
    return;
  }

  String command = Serial.readStringUntil('\n');
  command.trim();
  command.toUpperCase();

  if (command == "PICK" || command == "OPEN") {
    moveAndReturn(PICK_ANGLE);
    Serial.println("OK PICK");
  } else if (command == "LEFT") {
    moveAndReturn(45);
    Serial.println("OK LEFT");
  } else if (command == "CENTER") {
    moveAndReturn(90);
    Serial.println("OK CENTER");
  } else if (command == "RIGHT") {
    moveAndReturn(135);
    Serial.println("OK RIGHT");
  } else {
    int angle = command.toInt();
    if (angle >= 0 && angle <= 180) {
      moveAndReturn(angle);
      Serial.print("OK ");
      Serial.println(angle);
    } else {
      Serial.println("ERR");
    }
  }
}
