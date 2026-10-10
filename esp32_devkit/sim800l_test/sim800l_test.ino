/*
  sim800l_test.ino
  ---------------------------------------------------------------
  Step-by-step SIM800L check for ESP32 (no extra libraries needed)

  Runs these checks automatically and prints PASS / FAIL:
    1. Modem answers AT commands      (wiring TX/RX, power)
    2. Supply voltage (AT+CBC)        (should be 3.6 - 4.3 V)
    3. SIM card ready (AT+CPIN?)      (SIM inserted, PIN lock off)
    4. Signal quality (AT+CSQ)        (antenna, coverage)
    5. Network registration (AT+CREG?)
    6. GPRS internet + IP address     (APN, data balance)
    7. TCP connection to the MQTT broker (the path the tracker uses)

  After the checks, the Serial Monitor becomes a pass-through:
  type any AT command (set line ending to "Both NL & CR").

  Wiring (same as the tracker):
    SIM800L TXD -> ESP32 GPIO26
    SIM800L RXD <- ESP32 GPIO27 (through 10k/20k divider)
    SIM800L RST -> ESP32 GPIO5  (optional)
    SIM800L VCC -> separate 4.0 V / 2 A supply + 1000 uF capacitor
    All GND connected together

  Serial Monitor: 115200 baud
  ---------------------------------------------------------------
*/

// ============ USER CONFIGURATION ============
const char* APN       = "gpinternet";      // GP "gpinternet", Robi/Airtel "internet", Banglalink "blweb"
const char* TEST_HOST = "broker.emqx.io";  // MQTT broker used by the tracker
const int   TEST_PORT = 1883;
#define MODEM_RX_PIN  26
#define MODEM_TX_PIN  27
#define MODEM_RST_PIN 5                    // -1 if RST is not connected
#define MODEM_BAUD    9600
// ============================================

HardwareSerial SerialAT(1);

// Send one AT command and collect the reply until OK / ERROR / FAIL / waitFor or timeout
String sendAT(const String& cmd, unsigned long timeoutMs = 2000, const char* waitFor = "OK") {
  while (SerialAT.available()) SerialAT.read();          // drop old data
  SerialAT.print(cmd);
  SerialAT.print("\r\n");
  String resp;
  unsigned long t0 = millis();
  while (millis() - t0 < timeoutMs) {
    while (SerialAT.available()) resp += (char)SerialAT.read();
    if (resp.indexOf(waitFor) >= 0 || resp.indexOf("ERROR") >= 0 || resp.indexOf("FAIL") >= 0) {
      delay(50);
      while (SerialAT.available()) resp += (char)SerialAT.read();
      break;
    }
  }
  resp.trim();
  Serial.printf(">> %s\n%s\n", cmd.c_str(), resp.length() ? resp.c_str() : "(no reply)");
  return resp;
}

// Extract the integer that follows "key" (e.g. "+CSQ: " -> 18)
int numberAfter(const String& s, const char* key, int nth = 0) {
  int p = s.indexOf(key);
  if (p < 0) return -1;
  p += strlen(key);
  for (int i = 0; i < nth; i++) { p = s.indexOf(',', p); if (p < 0) return -1; p++; }
  return s.substring(p).toInt();
}

void result(const char* name, bool ok, const String& note) {
  Serial.printf("   [%s] %s %s\n\n", ok ? "PASS" : "FAIL", name, note.c_str());
}

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("\n=== SIM800L test ===\n");
  SerialAT.begin(MODEM_BAUD, SERIAL_8N1, MODEM_RX_PIN, MODEM_TX_PIN);

  if (MODEM_RST_PIN >= 0) {                 // hardware reset, then wait for boot
    pinMode(MODEM_RST_PIN, OUTPUT);
    digitalWrite(MODEM_RST_PIN, LOW);  delay(300);
    digitalWrite(MODEM_RST_PIN, HIGH);
  }
  Serial.println("Waiting 5 s for the modem to boot ...\n");
  delay(5000);

  // 1. AT (SIM800L auto-detects the baud rate from the first "AT")
  bool atOk = false;
  for (int i = 0; i < 10 && !atOk; i++) atOk = sendAT("AT", 1000).indexOf("OK") >= 0;
  result("Modem responds", atOk, atOk ? "" :
         "-> check: 4.0 V supply, common GND, SIM TXD->GPIO26, RXD->GPIO27, module LED blinking?");
  if (!atOk) { Serial.println("Stopping. Fix the above and press EN/RESET."); return; }

  sendAT("ATE0");                           // no echo -> cleaner replies
  sendAT("ATI");                            // module name / firmware

  // 2. Supply voltage
  String r = sendAT("AT+CBC");
  int mv = numberAfter(r, "+CBC: ", 2);
  result("Supply voltage", mv >= 3600 && mv <= 4300,
         String("= ") + mv + " mV" + (mv > 0 && mv < 3600 ? " -> too low, modem will reset during TX" : ""));

  // 3. SIM card
  r = sendAT("AT+CPIN?");
  bool simOk = r.indexOf("READY") >= 0;
  result("SIM ready", simOk, simOk ? "" : "-> SIM inserted correctly? PIN lock disabled?");

  // 4. Signal quality (0-31, 99 = unknown)
  r = sendAT("AT+CSQ");
  int csq = numberAfter(r, "+CSQ: ");
  const char* q = (csq == 99 || csq < 0) ? "no signal (antenna?)" : csq < 10 ? "weak" : csq < 15 ? "OK" : csq < 20 ? "good" : "excellent";
  result("Signal", csq >= 10 && csq != 99, String("CSQ = ") + csq + " (" + q + ")");

  // 5. Network registration (wait up to 60 s)
  bool regOk = false;
  for (int i = 0; i < 20 && !regOk; i++) {
    r = sendAT("AT+CREG?");
    int stat = numberAfter(r, "+CREG: ", 1);
    regOk = (stat == 1 || stat == 5);         // 1 = home, 5 = roaming
    if (!regOk) delay(3000);
  }
  sendAT("AT+COPS?");                         // operator name
  result("Registered on 2G network", regOk, regOk ? "" : "-> no 2G coverage / SIM blocked / weak signal / low power");
  if (!regOk) { Serial.println("Stopping before GPRS. Type AT commands below to investigate."); return; }

  // 6. GPRS internet
  sendAT("AT+CIPSHUT", 5000, "SHUT OK");
  sendAT("AT+CGATT=1", 10000);
  sendAT(String("AT+CSTT=\"") + APN + "\"");
  r = sendAT("AT+CIICR", 30000);
  r = sendAT("AT+CIFSR", 5000, ".");          // replies with the IP address (no OK)
  bool ipOk = r.indexOf('.') > 0 && r.indexOf("ERROR") < 0;
  result("GPRS internet", ipOk, ipOk ? String("IP = ") + r : String("-> check APN (\"") + APN + "\") and data balance");

  // 7. TCP connection to the MQTT broker
  if (ipOk) {
    r = sendAT(String("AT+CIPSTART=\"TCP\",\"") + TEST_HOST + "\"," + TEST_PORT, 20000, "CONNECT");
    bool tcpOk = r.indexOf("CONNECT OK") >= 0 || r.indexOf("ALREADY CONNECT") >= 0;
    result("TCP to MQTT broker", tcpOk, String(TEST_HOST) + ":" + TEST_PORT +
           (tcpOk ? " -> the tracker will work" : " -> blocked or DNS failed"));
    sendAT("AT+CIPCLOSE", 3000);
    sendAT("AT+CIPSHUT", 5000, "SHUT OK");
  }

  Serial.println("=== Checks done. You can now type AT commands (line ending: Both NL & CR) ===");
}

void loop() {
  // Pass-through between the Serial Monitor and the modem
  while (Serial.available())   SerialAT.write(Serial.read());
  while (SerialAT.available()) Serial.write(SerialAT.read());
}
