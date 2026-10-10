/*
  mqtt_sim800l_tracker.ino
  ---------------------------------------------------------------
  ESP32 + NEO-M8N + SIM800L live tracker - 2G GPRS, MQTT version

  Same broker, topics and JSON as mqtt_wifi_tracker, so the same web
  page (web/index.html) shows it. MQTT runs over plain TCP port 1883,
  which SIM800L supports (no TLS needed).

  Topics (TRACKER_KEY must match the key entered in the web page):
    gpstrk/<TRACKER_KEY>/<DEVICE_ID>/loc     JSON position (retained)
    gpstrk/<TRACKER_KEY>/<DEVICE_ID>/status  "online" / "offline" (retained, last will)

  Wiring
    NEO-M8N TX -> GPIO16, RX -> GPIO17, VCC -> VIN (5V), GND -> GND
    SIM800L VCC -> separate 4.0 V / >= 2 A supply + 1000 uF capacitor (NOT the ESP32 pins)
    SIM800L GND -> common GND
    SIM800L TXD -> GPIO26
    SIM800L RXD <- GPIO27 through a divider (10k from ESP32, 20k to GND)
    SIM800L RST -> GPIO5 (optional)

  Libraries (Library Manager):
    TinyGPSPlus  by Mikal Hart
    TinyGSM      by Volodymyr Shymanskyy
    PubSubClient by Nick O'Leary

  Serial Monitor: 115200 baud
  ---------------------------------------------------------------
*/

#define TINY_GSM_MODEM_SIM800
#define TINY_GSM_RX_BUFFER 1024
// #define DUMP_AT_COMMANDS          // uncomment to print every AT command

#include <TinyGsmClient.h>
#include <PubSubClient.h>
#include <TinyGPSPlus.h>

// =============== USER CONFIGURATION ===============
// APN: Grameenphone "gpinternet", Robi/Airtel "internet", Banglalink "blweb"
const char APN[]       = "gpinternet";
const char GPRS_USER[] = "";
const char GPRS_PASS[] = "";

const char* MQTT_HOST     = "broker.emqx.io";
const uint16_t MQTT_PORT  = 1883;
const char* TRACKER_KEY   = "change-this-secret-key"; // same key as the Wi-Fi sketch / web page
const char* DEVICE_ID     = "car-01";

#define GPS_RX_PIN        16
#define GPS_TX_PIN        17
#define GPS_BAUD          9600
#define MODEM_RX_PIN      26
#define MODEM_TX_PIN      27
#define MODEM_RST_PIN     5        // -1 if not connected
#define MODEM_BAUD        9600
#define SEND_INTERVAL_MS  5000
#define FIX_MAX_AGE_MS    3000
#define LED_PIN           2
// ==================================================

HardwareSerial GPSSerial(2);
HardwareSerial SerialAT(1);

#ifdef DUMP_AT_COMMANDS
  #include <StreamDebugger.h>
  StreamDebugger debugger(SerialAT, Serial);
  TinyGsm modem(debugger);
#else
  TinyGsm modem(SerialAT);
#endif

TinyGsmClient gsmClient(modem);
PubSubClient mqtt(gsmClient);
TinyGPSPlus gps;

char topicLoc[128], topicStatus[128];
unsigned long lastSend = 0, lastMqttAttempt = 0;
uint32_t sentOk = 0, sentFail = 0, mqttFailures = 0;

void feedGPS() { while (GPSSerial.available()) gps.encode(GPSSerial.read()); }
void smartDelay(unsigned long ms) { unsigned long t0 = millis(); while (millis() - t0 < ms) { feedGPS(); delay(5); } }

// ---------- JSON payload (same format for every tracker version) ----------
String buildPayload(bool& hasFix) {
  hasFix = gps.location.isValid() && gps.location.age() < FIX_MAX_AGE_MS;
  String json;
  json.reserve(320);
  json += "{\"device_id\":\""; json += DEVICE_ID;
  json += "\",\"fix\":";       json += hasFix ? "true" : "false";
  if (hasFix) {
    json += ",\"lat\":"; json += String(gps.location.lat(), 6);
    json += ",\"lng\":"; json += String(gps.location.lng(), 6);
    if (gps.speed.isValid())    { json += ",\"speed_kmh\":"; json += String(gps.speed.kmph(), 2); }
    if (gps.course.isValid())   { json += ",\"course\":";    json += String(gps.course.deg(), 1); }
    if (gps.altitude.isValid()) { json += ",\"alt_m\":";     json += String(gps.altitude.meters(), 1); }
  }
  if (gps.satellites.isValid()) { json += ",\"sats\":"; json += String(gps.satellites.value()); }
  if (gps.hdop.isValid())       { json += ",\"hdop\":"; json += String(gps.hdop.hdop(), 2); }
  if (gps.date.isValid() && gps.time.isValid() && gps.date.year() > 2000) {
    char t[24];
    snprintf(t, sizeof(t), "%04d-%02d-%02dT%02d:%02d:%02dZ",
             gps.date.year(), gps.date.month(), gps.date.day(),
             gps.time.hour(), gps.time.minute(), gps.time.second());
    json += ",\"gps_time\":\""; json += t; json += "\"";
  }
  json += "}";
  return json;
}

// ---------- Modem / GPRS ----------
void modemHardReset() {
  if (MODEM_RST_PIN < 0) return;
  pinMode(MODEM_RST_PIN, OUTPUT);
  digitalWrite(MODEM_RST_PIN, LOW);  delay(300);
  digitalWrite(MODEM_RST_PIN, HIGH);
  smartDelay(5000);                    // SIM800L needs ~5 s to boot after a reset
}

// Send a raw AT command and wait for OK/ERROR (same handshake as sim800l_test,
// which is more tolerant than TinyGSM's init() on some SIM800L boards)
bool rawAT(const char* cmd, unsigned long timeoutMs = 1000) {
  while (SerialAT.available()) SerialAT.read();
  SerialAT.print(cmd);
  SerialAT.print("\r\n");
  String resp;
  unsigned long t0 = millis();
  while (millis() - t0 < timeoutMs) {
    while (SerialAT.available()) resp += (char)SerialAT.read();
    if (resp.indexOf("OK") >= 0) return true;
    if (resp.indexOf("ERROR") >= 0) return false;
    feedGPS();
  }
  return false;
}

bool modemStart() {
  Serial.println("Initializing modem ...");
  // SIM800L locks its baud rate on the first "AT"; try several times
  bool ok = false;
  for (int i = 0; i < 15 && !ok; i++) {
    ok = rawAT("AT");
    if (!ok) smartDelay(500);
  }
  if (!ok) {
    Serial.println("  Modem not responding: check 4.0 V / 2 A supply and TX/RX wiring");
    return false;
  }
  rawAT("ATE0");                       // echo off (TinyGSM expects this)
  rawAT("AT+CMEE=2");                  // verbose error messages
  Serial.print("  Modem: "); Serial.println(modem.getModemInfo());
  if (modem.getSimStatus() != 1) { Serial.println("  SIM not ready (inserted? PIN lock off?)"); return false; }
  return true;
}

bool gprsReady() {
  if (!modem.isNetworkConnected()) {
    Serial.print("Waiting for 2G network ...");
    if (!modem.waitForNetwork(60000L)) { Serial.printf(" failed (CSQ %d)\n", modem.getSignalQuality()); return false; }
    Serial.printf(" OK. Operator: %s  CSQ: %d\n", modem.getOperator().c_str(), modem.getSignalQuality());
  }
  if (!modem.isGprsConnected()) {
    Serial.printf("Connecting GPRS (APN \"%s\") ...", APN);
    if (!modem.gprsConnect(APN, GPRS_USER, GPRS_PASS)) { Serial.println(" failed"); return false; }
    Serial.print(" OK. IP: "); Serial.println(modem.localIP());
  }
  return true;
}

// ---------- MQTT ----------
void maintainMqtt() {
  if (mqtt.connected()) return;
  if (lastMqttAttempt != 0 && millis() - lastMqttAttempt < 10000) return;
  lastMqttAttempt = millis();
  if (!gprsReady()) { mqttFailures++; return; }

  String clientId = String("trk-") + DEVICE_ID + "-" + String((uint32_t)ESP.getEfuseMac(), HEX);
  Serial.printf("Connecting to MQTT %s:%u ... ", MQTT_HOST, MQTT_PORT);
  if (mqtt.connect(clientId.c_str(), nullptr, nullptr, topicStatus, 0, true, "offline")) {
    Serial.println("OK");
    mqtt.publish(topicStatus, "online", true);
    mqttFailures = 0;
  } else {
    Serial.printf("failed (state %d)\n", mqtt.state());
    mqttFailures++;
  }

  // Recover a stuck modem: re-open GPRS after 3 failures, hardware reset after 6
  if (mqttFailures == 3) { Serial.println("-> reconnecting GPRS"); modem.gprsDisconnect(); }
  if (mqttFailures >= 6) { Serial.println("-> resetting modem"); modemHardReset(); modemStart(); mqttFailures = 0; }
}

void sendReport() {
  bool hasFix;
  String payload = buildPayload(hasFix);
  bool ok = mqtt.connected() && mqtt.publish(topicLoc, payload.c_str(), true);
  if (ok) { sentOk++; digitalWrite(LED_PIN, HIGH); delay(30); digitalWrite(LED_PIN, LOW); }
  else    { sentFail++; }
  Serial.printf("[%s] %s -> %s (ok %lu / fail %lu)\n", hasFix ? "FIX" : "NO FIX", payload.c_str(),
                ok ? "published" : "NOT sent", (unsigned long)sentOk, (unsigned long)sentFail);
}

void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println("\n=== ESP32 GPS tracker (SIM800L + MQTT) ===");
  pinMode(LED_PIN, OUTPUT);

  GPSSerial.setRxBufferSize(2048);     // modem calls block for seconds; keep GPS bytes
  GPSSerial.begin(GPS_BAUD, SERIAL_8N1, GPS_RX_PIN, GPS_TX_PIN);
  SerialAT.begin(MODEM_BAUD, SERIAL_8N1, MODEM_RX_PIN, MODEM_TX_PIN);

  snprintf(topicLoc, sizeof(topicLoc), "gpstrk/%s/%s/loc", TRACKER_KEY, DEVICE_ID);
  snprintf(topicStatus, sizeof(topicStatus), "gpstrk/%s/%s/status", TRACKER_KEY, DEVICE_ID);
  Serial.printf("Publishing to topic: %s\n", topicLoc);

  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setBufferSize(512);
  mqtt.setKeepAlive(60);               // GPRS links are slow; be tolerant
  mqtt.setSocketTimeout(15);

  modemHardReset();
  while (!modemStart()) { Serial.println("Retrying modem in 10 s ..."); smartDelay(10000); }
}

void loop() {
  feedGPS();
  maintainMqtt();
  mqtt.loop();

  if (millis() - lastSend >= SEND_INTERVAL_MS) {
    lastSend = millis();
    sendReport();
  }
}
