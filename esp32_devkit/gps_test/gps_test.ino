/*
  gps_test.ino
  ---------------------------------------------------------------
  NEO-M8N GPS module test for ESP32 (Arduino IDE)

  Purpose:
    1. Auto-detect the GPS baud rate (confirms wiring + module is alive)
    2. Optionally dump raw NMEA sentences (RAW_MODE = true)
    3. Print parsed position, satellites, speed, time every 2 seconds

  Wiring:
    NEO-M8N VCC -> ESP32 3V3 (or VIN/5V if your board has an onboard regulator)
    NEO-M8N GND -> ESP32 GND
    NEO-M8N TX  -> ESP32 GPIO16  (ESP32 RX2)
    NEO-M8N RX  -> ESP32 GPIO17  (ESP32 TX2)
    (TX goes to RX and RX goes to TX — crossed)

  Library required (Arduino IDE -> Library Manager):
    TinyGPSPlus by Mikal Hart

  Serial Monitor: 115200 baud
  ---------------------------------------------------------------
*/

#include <TinyGPSPlus.h>

// ---------- Configuration ----------
#define GPS_RX_PIN 16          // ESP32 pin that receives data from GPS TX
#define GPS_TX_PIN 17          // ESP32 pin that sends data to GPS RX
#define RAW_MODE   false       // true = print raw NMEA sentences, false = parsed output
#define PRINT_INTERVAL_MS 2000 // how often parsed data is printed
#define LOCAL_UTC_OFFSET 6     // Bangladesh Standard Time = UTC+6

// Common baud rates for u-blox modules (NEO-M8N default is 9600)
const uint32_t BAUD_CANDIDATES[] = {9600, 38400, 57600, 115200, 4800};

TinyGPSPlus gps;
HardwareSerial GPSSerial(2);   // use UART2 of the ESP32

uint32_t gpsBaud = 0;
unsigned long lastPrint = 0;
unsigned long bootTime = 0;
bool firstFixReported = false;

// Try each baud rate and check whether valid NMEA (correct checksum) arrives.
uint32_t detectBaud() {
  for (uint32_t baud : BAUD_CANDIDATES) {
    Serial.printf("Trying %lu baud ... ", (unsigned long)baud);
    GPSSerial.begin(baud, SERIAL_8N1, GPS_RX_PIN, GPS_TX_PIN);
    delay(100);
    while (GPSSerial.available()) GPSSerial.read();   // flush garbage

    TinyGPSPlus probe;
    unsigned long start = millis();
    while (millis() - start < 2500) {
      while (GPSSerial.available()) probe.encode(GPSSerial.read());
      if (probe.passedChecksum() >= 3) {
        Serial.println("OK (valid NMEA received)");
        return baud;
      }
    }
    Serial.printf("no valid data (chars seen: %lu)\n", (unsigned long)probe.charsProcessed());
    GPSSerial.end();
  }
  return 0;
}

void printParsed() {
  Serial.println(F("--------------------------------------------------"));
  Serial.printf("Uptime: %lus | chars: %lu | good sentences: %lu | bad checksum: %lu\n",
                (millis() - bootTime) / 1000,
                (unsigned long)gps.charsProcessed(),
                (unsigned long)gps.passedChecksum(),
                (unsigned long)gps.failedChecksum());

  // Satellites and HDOP (lower HDOP = better accuracy; < 2 is good)
  Serial.print(F("Satellites: "));
  if (gps.satellites.isValid()) Serial.print(gps.satellites.value());
  else Serial.print(F("--"));
  Serial.print(F("   HDOP: "));
  if (gps.hdop.isValid()) Serial.println(gps.hdop.hdop(), 2);
  else Serial.println(F("--"));

  // Position
  if (gps.location.isValid()) {
    if (!firstFixReported) {
      Serial.printf(">>> FIRST FIX acquired after %lu seconds <<<\n",
                    (millis() - bootTime) / 1000);
      firstFixReported = true;
    }
    Serial.printf("Location : %.6f, %.6f  (age %lu ms)\n",
                  gps.location.lat(), gps.location.lng(),
                  (unsigned long)gps.location.age());
    Serial.printf("Map link : https://maps.google.com/?q=%.6f,%.6f\n",
                  gps.location.lat(), gps.location.lng());
  } else {
    Serial.println(F("Location : NO FIX yet (go outdoors / near a window)"));
  }

  if (gps.altitude.isValid())
    Serial.printf("Altitude : %.1f m\n", gps.altitude.meters());
  if (gps.speed.isValid())
    Serial.printf("Speed    : %.2f km/h\n", gps.speed.kmph());
  if (gps.course.isValid())
    Serial.printf("Course   : %.1f deg\n", gps.course.deg());

  // Date and time (GPS gives UTC; converted to local time for display)
  if (gps.date.isValid() && gps.time.isValid() && gps.date.year() > 2000) {
    int localHour = (gps.time.hour() + LOCAL_UTC_OFFSET) % 24;
    Serial.printf("UTC      : %04d-%02d-%02d %02d:%02d:%02d\n",
                  gps.date.year(), gps.date.month(), gps.date.day(),
                  gps.time.hour(), gps.time.minute(), gps.time.second());
    Serial.printf("Local    : %02d:%02d:%02d (UTC+%d)\n",
                  localHour, gps.time.minute(), gps.time.second(), LOCAL_UTC_OFFSET);
  } else {
    Serial.println(F("Time     : not available yet"));
  }
}

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println();
  Serial.println(F("=== NEO-M8N GPS test (ESP32) ==="));

  gpsBaud = detectBaud();
  if (gpsBaud == 0) {
    Serial.println();
    Serial.println(F("ERROR: No valid data from GPS on any baud rate."));
    Serial.println(F("Check: 1) VCC/GND  2) GPS TX -> GPIO16  3) GPS RX -> GPIO17"));
    Serial.println(F("       4) Module power LED is on  5) Swap TX/RX if unsure"));
    Serial.println(F("Halting. Fix wiring and press EN/RESET."));
    while (true) delay(1000);
  }

  GPSSerial.begin(gpsBaud, SERIAL_8N1, GPS_RX_PIN, GPS_TX_PIN);
  Serial.printf("GPS communication OK at %lu baud. Waiting for satellite fix...\n",
                (unsigned long)gpsBaud);
  Serial.println(F("(Cold start outdoors usually takes 30-60 s; indoors may never fix)"));
  bootTime = millis();
}

void loop() {
  // Feed every incoming byte to the parser (and echo it in raw mode)
  while (GPSSerial.available()) {
    char c = GPSSerial.read();
    if (RAW_MODE) Serial.write(c);
    gps.encode(c);
  }

  if (!RAW_MODE && millis() - lastPrint >= PRINT_INTERVAL_MS) {
    lastPrint = millis();
    printParsed();
  }
}
