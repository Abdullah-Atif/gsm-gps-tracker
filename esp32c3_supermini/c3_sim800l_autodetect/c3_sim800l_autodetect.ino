/*
  c3_sim800l_autodetect.ino  (ESP32-C3 Super Mini version)
  ---------------------------------------------------------------
  Finds how your SIM800L is connected - no rewiring needed.

  Garbage characters (e.g. "⸮⸮⸮") from the modem usually mean a baud-rate
  mismatch (the module may have been set to a fixed baud rate before),
  and no reply at all can mean TX/RX are swapped. This sketch tries
  BOTH pin orientations (4/3 and 3/4) at every common baud rate
  until the modem answers "OK".

  When found, it:
    1. prints the correct MODEM_RX_PIN / MODEM_TX_PIN / baud
    2. sets the modem permanently to 9600 baud (AT+IPR=9600, AT&W),
       which is what the test and tracker sketches use
    3. switches to pass-through mode so you can type AT commands
       (Serial Monitor line ending: "Both NL & CR")

  No libraries needed. Serial Monitor: 115200 baud.
  Arduino IDE: Board "ESP32C3 Dev Module", Tools -> USB CDC On Boot: "Enabled".
  ---------------------------------------------------------------
*/

#define PIN_A          4      // C3 PCB v2: GPIO4 <- SIM800L TXD
#define PIN_B          3      // C3 PCB v2: GPIO3 -> divider -> SIM800L RXD
#define MODEM_RST_PIN  2      // -1 if RST is not connected
#define TARGET_BAUD    9600   // baud rate used by the other sketches

const long BAUDS[] = {9600, 115200, 57600, 38400, 19200, 4800, 2400, 1200};

HardwareSerial SerialAT(1);
int foundRx = -1, foundTx = -1;
long foundBaud = 0;

// Show non-printable bytes as <hex> so garbage is visible in the log
String printable(const String& s) {
  String out;
  for (unsigned int i = 0; i < s.length(); i++) {
    uint8_t c = s[i];
    if (c == '\r') continue;
    if (c == '\n') { out += ' '; continue; }
    if (c >= 32 && c < 127) out += (char)c;
    else { char b[6]; snprintf(b, sizeof(b), "<%02X>", c); out += b; }
  }
  out.trim();
  return out;
}

// Open the UART with the given pins/baud and send "AT" up to 3 times
bool tryAT(int rx, int tx, long baud, String& reply) {
  SerialAT.end();
  delay(50);
  SerialAT.begin(baud, SERIAL_8N1, rx, tx);
  delay(100);
  for (int i = 0; i < 3; i++) {
    while (SerialAT.available()) SerialAT.read();
    SerialAT.print("AT\r\n");
    reply = "";
    unsigned long t0 = millis();
    while (millis() - t0 < 600) {
      while (SerialAT.available()) reply += (char)SerialAT.read();
      if (reply.indexOf("OK") >= 0) return true;
    }
  }
  return false;
}

// Send a command at the current settings and print the reply
String cmd(const char* c, unsigned long timeoutMs = 1500) {
  while (SerialAT.available()) SerialAT.read();
  SerialAT.print(c); SerialAT.print("\r\n");
  String r; unsigned long t0 = millis();
  while (millis() - t0 < timeoutMs) {
    while (SerialAT.available()) r += (char)SerialAT.read();
    if (r.indexOf("OK") >= 0 || r.indexOf("ERROR") >= 0) break;
  }
  Serial.printf("   >> %s  ->  %s\n", c, r.length() ? printable(r).c_str() : "(no reply)");
  return r;
}

void setup() {
  Serial.begin(115200);
  delay(1500);                          // wait for the native-USB Serial Monitor
  Serial.println("\n=== SIM800L auto-detect (pins + baud) ===\n");

  if (MODEM_RST_PIN >= 0) {
    pinMode(MODEM_RST_PIN, OUTPUT);
    digitalWrite(MODEM_RST_PIN, LOW);  delay(300);
    digitalWrite(MODEM_RST_PIN, HIGH);
  }
  Serial.println("Waiting 6 s for the modem to boot ...\n");
  delay(6000);

  const int orient[2][2] = {{PIN_A, PIN_B}, {PIN_B, PIN_A}};   // {rx, tx}
  for (int o = 0; o < 2 && foundBaud == 0; o++) {
    int rx = orient[o][0], tx = orient[o][1];
    Serial.printf("Orientation %d: ESP32 RX=GPIO%d (to SIM TXD), ESP32 TX=GPIO%d (to SIM RXD)\n", o + 1, rx, tx);
    for (long baud : BAUDS) {
      String reply;
      bool ok = tryAT(rx, tx, baud, reply);
      Serial.printf("   %6ld baud: %s\n", baud,
                    ok ? "OK  <== FOUND" : (reply.length() ? ("reply: " + printable(reply)).c_str() : "no reply"));
      if (ok) { foundRx = rx; foundTx = tx; foundBaud = baud; break; }
    }
    Serial.println();
  }

  if (foundBaud == 0) {
    Serial.println("NOT FOUND in any orientation / baud. Check:");
    Serial.println("  - SIM800L GND and ESP32 GND connected together (most common cause!)");
    Serial.println("  - Super Mini plugged in the right way (5V/GND pins next to USB, see PCB silkscreen)");
    Serial.println("  - 10k/20k divider: 10k between ESP32 TX pin and SIM RXD, 20k from SIM RXD to GND");
    Serial.println("  - RST pin not held LOW (disconnect RST and set MODEM_RST_PIN -1 to test)");
    return;
  }

  Serial.println("==============================================================");
  Serial.printf(" FOUND: modem answers at %ld baud\n", foundBaud);
  Serial.printf(" Wiring that works: SIM TXD -> GPIO%d,  SIM RXD -> GPIO%d\n", foundRx, foundTx);
  Serial.println(" In c3_mqtt_sim800l_tracker.ino set:");
  Serial.printf("   #define MODEM_RX_PIN  %d\n   #define MODEM_TX_PIN  %d\n", foundRx, foundTx);
  Serial.println("==============================================================\n");

  if (foundBaud != TARGET_BAUD) {
    Serial.printf("Setting the modem permanently to %d baud ...\n", TARGET_BAUD);
    char c[24]; snprintf(c, sizeof(c), "AT+IPR=%d", TARGET_BAUD);
    cmd(c);
    SerialAT.end(); delay(100);
    SerialAT.begin(TARGET_BAUD, SERIAL_8N1, foundRx, foundTx);
    delay(300);
    cmd("AT");
    cmd("AT&W");                        // save the setting in the modem
    foundBaud = TARGET_BAUD;
  }

  Serial.println("\nQuick checks:");
  cmd("ATI");
  cmd("AT+CPIN?");
  cmd("AT+CSQ");
  cmd("AT+CREG?");
  cmd("AT+CBC");
  Serial.println("\nDone. Type AT commands below (line ending: Both NL & CR).");
}

void loop() {
  if (foundBaud == 0) return;
  while (Serial.available())   SerialAT.write(Serial.read());
  while (SerialAT.available()) Serial.write(SerialAT.read());
}
