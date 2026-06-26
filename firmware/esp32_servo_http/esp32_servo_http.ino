#include <WiFi.h>
#include <WebServer.h>
#include <ESP32Servo.h>

const char* WIFI_SSID = "SEU_WIFI";
const char* WIFI_PASSWORD = "SUA_SENHA";

const int SERVO_PIN = 13;
const int HOME_ANGLE = 0;
const int PICK_ANGLE = 90;
const unsigned long HOLD_MS = 1000;

WebServer server(80);
Servo clawServo;

void moveAndReturn(int angle) {
  angle = constrain(angle, 0, 180);
  clawServo.write(angle);
  delay(HOLD_MS);
  clawServo.write(HOME_ANGLE);
  delay(300);
}

void handlePick() {
  moveAndReturn(PICK_ANGLE);
  server.send(200, "text/plain", "OK PICK");
}

void handleLeft() {
  moveAndReturn(45);
  server.send(200, "text/plain", "OK LEFT");
}

void handleCenter() {
  moveAndReturn(90);
  server.send(200, "text/plain", "OK CENTER");
}

void handleRight() {
  moveAndReturn(135);
  server.send(200, "text/plain", "OK RIGHT");
}

void handleServo() {
  if (!server.hasArg("angle")) {
    server.send(400, "text/plain", "Missing angle");
    return;
  }

  int angle = server.arg("angle").toInt();
  if (angle < 0 || angle > 180) {
    server.send(400, "text/plain", "Invalid angle");
    return;
  }

  moveAndReturn(angle);
  server.send(200, "text/plain", "OK");
}

void setup() {
  Serial.begin(115200);

  clawServo.setPeriodHertz(50);
  clawServo.attach(SERVO_PIN, 500, 2400);
  clawServo.write(HOME_ANGLE);

  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();
  Serial.print("Servo controller IP: ");
  Serial.println(WiFi.localIP());

  server.on("/pick", handlePick);
  server.on("/open", handlePick);
  server.on("/left", handleLeft);
  server.on("/center", handleCenter);
  server.on("/right", handleRight);
  server.on("/servo", handleServo);
  server.begin();
}

void loop() {
  server.handleClient();
}
