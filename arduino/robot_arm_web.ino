#include <Servo.h>

Servo servos[6];
int pins[6] = {3, 5, 6, 9, 10, 11};
int angles[6] = {90, 90, 90, 90, 90, 90};

void setup() {
  Serial.begin(9600);
  for (int i = 0; i < 6; i++) {
    servos[i].attach(pins[i]);
    servos[i].write(90);
  }
  delay(500);
  Serial.println("READY");
}

void loop() {
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();

    // Format: S<1-6>:<0-180>  e.g. "S1:90"
    if (cmd.length() >= 4 && cmd.charAt(0) == 'S') {
      int colonIdx = cmd.indexOf(':');
      if (colonIdx > 1) {
        int servoNum = cmd.substring(1, colonIdx).toInt();
        int angle    = cmd.substring(colonIdx + 1).toInt();
        if (servoNum >= 1 && servoNum <= 6 && angle >= 0 && angle <= 180) {
          angles[servoNum - 1] = angle;
          servos[servoNum - 1].write(angle);
          Serial.println("OK");
        } else {
          Serial.println("ERR:range");
        }
      }
    } else if (cmd == "HOME") {
      for (int i = 0; i < 6; i++) {
        servos[i].write(90);
        angles[i] = 90;
        delay(100);
      }
      Serial.println("OK");
    } else if (cmd == "STATUS") {
      for (int i = 0; i < 6; i++) {
        Serial.print("S");
        Serial.print(i + 1);
        Serial.print(":");
        Serial.println(angles[i]);
      }
    }
  }
}
