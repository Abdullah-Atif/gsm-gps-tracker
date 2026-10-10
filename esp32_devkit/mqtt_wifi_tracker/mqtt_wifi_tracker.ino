/*
  mqtt_wifi_tracker.ino
  ---------------------------------------------------------------
  ESP32 + NEO-M8N live tracker - Wi-Fi / phone hotspot, MQTT version

  Publishes the GPS position every SEND_INTERVAL_MS to a free public
  MQTT broker (plain TCP, port 1883). The web page (web/index.html)
  subscribes to the same broker, so no server or PC is needed.
  The SIM800L version (mqtt_sim800l_tracker) uses the same broker,
  topics and JSON, so the web page works for both.

  Topics (TRACKER_KEY must match the key entered in the web page):
    gpstrk/<TRACKER_KEY>/<DEVICE_ID>/loc     JSON position (retained)
    gpstrk/<TRACKER_KEY>/<DEVICE_ID>/status  "online" / "offline" (retained, last will)

  Wiring:
    NEO-M8N TX -> GPIO16, NEO-M8N RX -> GPIO17, VCC -> VIN (5V), GND -> GND

  Libraries (Library Manager):
    TinyGPSPlus  by Mikal Hart
    PubSubClient by Nick O'Leary

  Serial Monitor: 115200 baud
  ---------------------------------------------------------------
*/

#include <WiFi.h>
#include <PubSubClient.h>
#include <TinyGPSPlus.h>

// =============== USER CONFIGURATION ===============
const char* WIFI_SSID     = "YOUR_HOTSPOT_NAME";     // 2.4 GHz only
const char* WIFI_PASSWORD = "YOUR_HOTSPOT_PASSWORD";

const char* MQTT_HOST     = "broker.emqx.io";        // free public broker
const uint16_t MQTT_PORT  = 1883;                    // plain TCP (same as SIM800L)
const char* TRACKER_KEY   = "change-this-secret-key"; // long random text; same key in the web page
const char* DEVICE_ID     = "car-01";

#define GPS_RX_PIN        16
#define GPS_TX_PIN        17
#define GPS_BAUD          9600
#define SEND_INTERVAL_MS  3000
#define FIX_MAX_AGE_MS    3000
#define LED_PIN           2
// ==================================================

TinyGPSPlus gps;
HardwareSerial GPSSerial(2);
WiFiClient net;
PubSubClient mqtt(net);

char topicLoc[128], topicStatus[128];
unsigned long lastSend = 0, lastWifiAttempt = 0, lastMqttAttempt = 0;
uint32_t sentOk = 0, sentFail = 0;

void feedGPS() { while (GPSSerial.available()) gps.encode(GPSSerial.read()); }

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

// ---------- Wi-Fi ----------
bool wifiWasConnected = false;
bool publicDnsApplied = false;   // true after switching to 8.8.8.8 / 1.1.1.1

const char* wifiStatusText(wl_status_t st) {
  switch (st) {
    case WL_CONNECTED:       return "connected";
    case WL_NO_SSID_AVAIL:   return "network not found (hotspot off / 5 GHz / wrong name)";
    case WL_CONNECT_FAILED:  return "connect failed (wrong password / WPA3)";
    case WL_CONNECTION_LOST: return "connection lost";
    case WL_DISCONNECTED:    return "disconnected / still connecting";
    case WL_IDLE_STATUS:     return "idle";
    default:                 return "unknown";
  }
}

const char* authText(wifi_auth_mode_t a) {
  switch (a) {
    case WIFI_AUTH_OPEN:          return "open";
    case WIFI_AUTH_WPA_PSK:       return "WPA";
    case WIFI_AUTH_WPA2_PSK:      return "WPA2";
    case WIFI_AUTH_WPA_WPA2_PSK:  return "WPA/WPA2";
    case WIFI_AUTH_WPA3_PSK:      return "WPA3 (may fail!)";
    case WIFI_AUTH_WPA2_WPA3_PSK: return "WPA2/WPA3";
    default:                      return "other";
  }
}

// Lists the 2.4 GHz networks the ESP32 can see, to diagnose hotspot problems
void scanNetworks() {
  Serial.println("Scanning Wi-Fi networks (ESP32 sees 2.4 GHz only) ...");
  int n = WiFi.scanNetworks();
  bool found = false;
  for (int i = 0; i < n; i++) {
    bool match = (WiFi.SSID(i) == WIFI_SSID);
    found |= match;
    Serial.printf("  %s %-26s ch %2d  %4d dBm  %s\n", match ? ">>" : "  ", WiFi.SSID(i).c_str(),
                  WiFi.channel(i), WiFi.RSSI(i), authText(WiFi.encryptionType(i)));
  }
  if (!found) Serial.printf("  !! \"%s\" NOT found. Set the hotspot band to 2.4 GHz and check the exact name.\n", WIFI_SSID);
  WiFi.scanDelete();
}

void maintainWiFi() {
  wl_status_t st = WiFi.status();
  if (st == WL_CONNECTED) {
    if (!wifiWasConnected) {
      wifiWasConnected = true;
      Serial.printf("Wi-Fi connected. IP: %s  RSSI: %d dBm\n", WiFi.localIP().toString().c_str(), WiFi.RSSI());
      Serial.printf("  Gateway: %s  DNS: %s  Subnet: %s\n", WiFi.gatewayIP().toString().c_str(),
                    WiFi.dnsIP(0).toString().c_str(), WiFi.subnetMask().toString().c_str());
      lastMqttAttempt = millis() - 3000;   // first MQTT attempt about 2 s from now
    }
    return;
  }
  if (wifiWasConnected) {
    wifiWasConnected = false;
    Serial.println("Wi-Fi lost");
    if (publicDnsApplied) {                     // back to DHCP for the next connection
      WiFi.config(INADDR_NONE, INADDR_NONE, INADDR_NONE);
      publicDnsApplied = false;
    }
  }
  // Give each attempt 20 s (phone hotspots can be slow to hand out an IP address)
  if (lastWifiAttempt != 0 && millis() - lastWifiAttempt < 20000) return;
  if (lastWifiAttempt != 0) Serial.printf("Wi-Fi not connected: %s\n", wifiStatusText(st));
  Serial.printf("Connecting to Wi-Fi \"%s\" ...\n", WIFI_SSID);
  WiFi.disconnect();
  delay(100);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  lastWifiAttempt = millis();
}

// ---------- MQTT ----------
// Explains *why* the broker cannot be reached (printed after a failed MQTT connect).
// Some phone hotspots hand out a DNS server that does not answer the ESP32;
// in that case we switch to public DNS (8.8.8.8 / 1.1.1.1) and keep using it.

void applyPublicDns() {
  IPAddress ip = WiFi.localIP(), gw = WiFi.gatewayIP(), mask = WiFi.subnetMask();
  WiFi.config(ip, gw, mask, IPAddress(8, 8, 8, 8), IPAddress(1, 1, 1, 1));
  publicDnsApplied = true;
  Serial.println("  -> switched DNS to 8.8.8.8 / 1.1.1.1");
}

void runNetworkDiagnostics() {
  WiFiClient t;
  // 1) Raw internet test by IP address (no DNS involved)
  bool netOk = t.connect(IPAddress(1, 1, 1, 1), 80, 5000);
  t.stop();
  Serial.printf("  Internet (1.1.1.1:80, no DNS) -> %s\n",
                netOk ? "OK" : "FAILED: phone has no internet (mobile data off / no balance / data saver)");

  // 2) DNS test; on failure retry with public DNS servers
  IPAddress ip;
  bool dnsOk = WiFi.hostByName(MQTT_HOST, ip) && !(ip == IPAddress(0, 0, 0, 0));
  Serial.printf("  DNS %s -> %s\n", MQTT_HOST, dnsOk ? ip.toString().c_str() : "FAILED");
  if (!dnsOk && netOk && !publicDnsApplied) {
    applyPublicDns();
    delay(500);
    dnsOk = WiFi.hostByName(MQTT_HOST, ip) && !(ip == IPAddress(0, 0, 0, 0));
    Serial.printf("  DNS (public) %s -> %s\n", MQTT_HOST, dnsOk ? ip.toString().c_str() : "FAILED");
  }

  // 3) Can we open the MQTT port?
  if (dnsOk) {
    bool portOk = t.connect(ip, MQTT_PORT, 5000);
    t.stop();
    Serial.printf("  TCP %s:%u -> %s\n", MQTT_HOST, MQTT_PORT,
                  portOk ? "OK (broker reachable, retrying MQTT)" : "FAILED (port blocked by the network?)");
  }
}

void maintainMqtt() {
  if (WiFi.status() != WL_CONNECTED || mqtt.connected()) return;
  if (lastMqttAttempt != 0 && millis() - lastMqttAttempt < 5000) return;
  lastMqttAttempt = millis();

  String clientId = String("trk-") + DEVICE_ID + "-" + String((uint32_t)ESP.getEfuseMac(), HEX);
  Serial.printf("Connecting to MQTT %s:%u ... ", MQTT_HOST, MQTT_PORT);
  // Last will: the broker publishes "offline" (retained) if the tracker disappears
  if (mqtt.connect(clientId.c_str(), nullptr, nullptr, topicStatus, 0, true, "offline")) {
    Serial.println("OK");
    mqtt.publish(topicStatus, "online", true);
  } else {
    Serial.printf("failed (state %d)\n", mqtt.state());
    runNetworkDiagnostics();
  }
}

void sendReport() {
  bool hasFix;
  String payload = buildPayload(hasFix);
  bool ok = mqtt.connected() && mqtt.publish(topicLoc, payload.c_str(), true);
  if (ok) { sentOk++; digitalWrite(LED_PIN, HIGH); delay(30); digitalWrite(LED_PIN, LOW); }
  else    { sentFail++; }
  Serial.printf("[%s] %s -> %s (ok %lu / fail %lu)\n", hasFix ? "FIX" : "NO FIX", payload.c_str(),
                ok ? "published" : "NOT sent (no Wi-Fi/MQTT)", (unsigned long)sentOk, (unsigned long)sentFail);
}

void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println("\n=== ESP32 GPS tracker (Wi-Fi + MQTT) ===");
  pinMode(LED_PIN, OUTPUT);

  GPSSerial.setRxBufferSize(2048);
  GPSSerial.begin(GPS_BAUD, SERIAL_8N1, GPS_RX_PIN, GPS_TX_PIN);

  snprintf(topicLoc, sizeof(topicLoc), "gpstrk/%s/%s/loc", TRACKER_KEY, DEVICE_ID);
  snprintf(topicStatus, sizeof(topicStatus), "gpstrk/%s/%s/status", TRACKER_KEY, DEVICE_ID);
  Serial.printf("Publishing to topic: %s\n", topicLoc);

  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  // Lower radio power = lower current peaks. Prevents resets on a weak USB supply;
  // 8.5 dBm is plenty when the phone hotspot is close. Remove if power is solid.
  WiFi.setTxPower(WIFI_POWER_8_5dBm);
  WiFi.setAutoReconnect(true);
  scanNetworks();
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setBufferSize(512);      // default 256 bytes is too small for the JSON
  mqtt.setKeepAlive(30);
  mqtt.setSocketTimeout(5);
}

void loop() {
  feedGPS();
  maintainWiFi();
  maintainMqtt();
  mqtt.loop();

  if (millis() - lastSend >= SEND_INTERVAL_MS) {
    lastSend = millis();
    if (gps.charsProcessed() < 10 && millis() > 5000) Serial.println("WARNING: no data from GPS - check wiring");
    sendReport();
  }
}
