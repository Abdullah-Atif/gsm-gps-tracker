/*
  c3_gps_test.ino
  ---------------------------------------------------------------
  NEO-M8N GPS check for the ESP32-C3 Super Mini (C3 carrier PCB pins)

    GPS TX -> GPIO1   (ESP32-C3 RX)
    GPS RX <- GPIO0   (ESP32-C3 TX)
    GPS 5V / GND from the carrier board

  Arduino IDE: Board "ESP32C3 Dev Module", Tools -> USB CDC On Boot: "Enabled".
  Library: TinyGPSPlus by Mikal Hart. Serial Monitor: 115200 baud.
  ---------------------------------------------------------------
*/

#include <TinyGPSPlus.h>

#define GPS_RX_PIN 1
#define GPS_TX_PIN 0
#define LED_PIN    8                     // on-board LED, active LOW

const uint32_t BAUDS[] = {9600, 38400, 57600, 115200, 4800};

TinyGPSPlus gps;
HardwareSerial GPSSerial(0);             // UART0 (Serial is native USB)
unsigned long lastPrint = 0;

uint32_t detectBaud() {
  for (uint32_t baud : BAUDS) {
    Serial.printf("Trying %lu baud ... ", (unsigned long)baud);
    GPSSerial.begin(baud, SERIAL_8N1, GPS_RX_PIN, GPS_TX_PIN);
    delay(100);
    TinyGPSPlus probe;
    unsigned long t0 = millis();
    while (millis() - t0 < 2500) {
      while (GPSSerial.available()) probe.encode(GPSSerial.read());
      if (probe.passedChecksum() >= 3) { Serial.println("OK"); return baud; }
    }
    Serial.printf("no valid data (%lu chars)\n", (unsigned long)probe.charsProcessed());
    GPSSerial.end();
  }
  return 0;
}

void setup() {
  Serial.begin(115200);
  delay(1500);                           // wait for the native-USB Serial Monitor
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, HIGH);
  Serial.println("\n=== ESP32-C3 GPS test ===");
  uint32_t baud = detectBaud();
  if (!baud) {
    Serial.println("No GPS data. Check GPS TX -> GPIO1, RX -> GPIO0, 5V and GND.");
    while (true) delay(1000);
  }
  GPSSerial.begin(baud, SERIAL_8N1, GPS_RX_PIN, GPS_TX_PIN);
}

void loop() {
  while (GPSSerial.available()) gps.encode(GPSSerial.read());
  if (millis() - lastPrint < 2000) return;
  lastPrint = millis();

  digitalWrite(LED_PIN, gps.location.isValid() ? LOW : HIGH);   // LED on = GPS fix
  Serial.printf("sats %s  hdop %s  ",
                gps.satellites.isValid() ? String(gps.satellites.value()).c_str() : "--",
                gps.hdop.isValid() ? String(gps.hdop.hdop(), 2).c_str() : "--");
  if (gps.location.isValid())
    Serial.printf("%.6f, %.6f  https://maps.google.com/?q=%.6f,%.6f\n",
                  gps.location.lat(), gps.location.lng(), gps.location.lat(), gps.location.lng());
  else
    Serial.println("no fix yet (go outdoors)");
}
