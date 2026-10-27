/*
  Chong trom thong minh - Phan 2: ESP32 + RFID RC522 + Servo + Coi + 2 LED
  Luong chinh: quet the -> doc UID -> POST len server -> nhan "allow" -> servo/LED/coi
  Nguyen tac: loi mang / loi API / thieu key => FAIL-CLOSED (khong mo cua)

  Thu vien can cai (Library Manager): MFRC522, ArduinoJson (v6 hoac v7), ESP32Servo
  Serial Monitor: 115200 baud, chon "Newline" o o nhap lenh.
  Lenh Serial (luu vao flash, giu sau khi khoi dong lai):
    show                 -> xem IP va key (key chi hien 4 ky tu cuoi)
    ip 192.168.1.50      -> doi IP server
    key <chuoi_key>      -> doi API key
    cfg <ip> <key>       -> doi ca hai trong mot dong
*/
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <SPI.h>
#include <MFRC522.h>
#include <ESP32Servo.h>
#include <Preferences.h>
// ======================= CAU HINH MANG =======================
const char *WIFI_SSID = "GiapHuong";          // hotspot 2.4 GHz
const char *WIFI_PASSWORD = "GIAPHUONG262";

String serverIp = "192.168.2.10";                 // mac dinh; ghi de bang lenh Serial
String apiKey = "";                                // do ban 3 cap, nhap bang lenh "key" hoac "cfg"
const uint16_t SERVER_PORT = 8000;                 // CHO BAN 3 XAC NHAN (FastAPI thuong la 8000)
const char *ACCESS_PATH = "/api/rfid/scan";     // CHO BAN 3 XAC NHAN
const char *API_KEY_HEADER = "X-API-Key";          // khong gui neu endpoint khong yeu cau key
const char *DEVICE_ID = "gate01";

constexpr uint16_t HTTP_TIMEOUT_MS = 3000;
constexpr unsigned long WIFI_CONNECT_TIMEOUT_MS = 10000;
constexpr unsigned long WIFI_RETRY_INTERVAL_MS = 10000;

// ======================= CHAN KET NOI =======================
// ESP32 VSPI: SS/SDA=GPIO5, SCK=18, MOSI=23, MISO=19.
constexpr uint8_t RFID_SS_PIN = 5;
constexpr uint8_t RFID_RST_PIN = 22;
constexpr uint8_t SERVO_PIN = 13;
constexpr uint8_t BUZZER_PIN = 27;     // Coi CHU DONG, kich muc HIGH (neu la coi thu dong phai doi sang tone())
constexpr uint8_t LED_GREEN_PIN = 25;  // xanh = cho phep (noi qua dien tro 220-330 ohm)
constexpr uint8_t LED_RED_PIN = 26;    // do = tu choi / loi (noi qua dien tro 220-330 ohm)

// ======================= SERVO =======================
constexpr int SERVO_CLOSED_ANGLE = 0;
constexpr int SERVO_OPEN_ANGLE = 90;
constexpr unsigned long SERVO_OPEN_MS = 2000;

// ======================= BIEN TOAN CUC =======================
unsigned long lastWiFiAttemptMs = 0;
bool lastAuthError = false;  // true neu lan goi API gan nhat bi server tu choi key (401/403) hoac chua co key
MFRC522 reader(RFID_SS_PIN, RFID_RST_PIN);
Servo lockServo;
Preferences prefs;

// ======================= TIEN ICH =======================
String uidToUpperHex(const MFRC522::Uid &uid) {
  String result;
  result.reserve(uid.size * 2);
  char byteText[3];
  for (byte i = 0; i < uid.size; ++i) {
    snprintf(byteText, sizeof(byteText), "%02X", uid.uidByte[i]);
    result += byteText;
  }
  return result;  // vi du: 04A1B2C3 (hex hoa, khong dau cach)
}

String maskKey(const String &key) {
  if (key.length() == 0) return "(chua dat)";
  if (key.length() <= 4) return "****";
  return "****" + key.substring(key.length() - 4);
}

void printConfig() {
  Serial.println("Server IP: " + serverIp);
  Serial.println("API key: " + maskKey(apiKey));
}

void loadConfig() {
  prefs.begin("cfg", false);
  serverIp = prefs.getString("srv_ip", serverIp);
  apiKey = prefs.getString("api_key", "");
  prefs.end();
  printConfig();
}

bool setServerIp(String newIp) {
  newIp.trim();
  IPAddress test;
  if (!test.fromString(newIp)) {
    Serial.println("IP khong hop le. Vi du: ip 192.168.1.50");
    return false;
  }
  prefs.begin("cfg", false);
  prefs.putString("srv_ip", newIp);
  prefs.end();
  serverIp = newIp;
  Serial.println("Da luu Server IP: " + serverIp);
  return true;
}

bool setApiKey(String newKey) {
  newKey.trim();
  if (newKey.length() == 0) {
    Serial.println("Key trong. Vi du: key abc123xyz");
    return false;
  }
  prefs.begin("cfg", false);
  prefs.putString("api_key", newKey);
  prefs.end();
  apiKey = newKey;
  Serial.println("Da luu API key: " + maskKey(apiKey));
  return true;
}

void handleSerialCommand() {
  if (!Serial.available()) return;
  String line = Serial.readStringUntil('\n');
  line.trim();
  if (line.length() == 0) return;

  if (line == "show" || line == "ip" || line == "key") {
    printConfig();
  } else if (line.startsWith("ip ")) {
    setServerIp(line.substring(3));
  } else if (line.startsWith("key ")) {
    setApiKey(line.substring(4));
  } else if (line.startsWith("cfg ")) {
    String rest = line.substring(4);
    rest.trim();
    const int sp = rest.indexOf(' ');
    if (sp < 0) {
      Serial.println("Cu phap: cfg <ip> <key>");
      return;
    }
    if (setServerIp(rest.substring(0, sp))) {
      setApiKey(rest.substring(sp + 1));
    }
  } else {
    Serial.println("Lenh: show | ip x.x.x.x | key <chuoi> | cfg <ip> <key>");
  }
}

// ======================= WIFI =======================
void connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  const unsigned long startedAt = millis();
  Serial.print("Dang ket noi Wi-Fi");
  while (WiFi.status() != WL_CONNECTED && millis() - startedAt < WIFI_CONNECT_TIMEOUT_MS) {
    delay(500);
    Serial.print('.');
  }
  Serial.println();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("Wi-Fi connected; ESP32 IP: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("Wi-Fi timeout; reader stays active, access remains fail-closed");
  }
  lastWiFiAttemptMs = millis();
}

void maintainWiFi() {
  if (WiFi.status() == WL_CONNECTED || millis() - lastWiFiAttemptMs < WIFI_RETRY_INTERVAL_MS) {
    return;
  }
  lastWiFiAttemptMs = millis();
  Serial.println("Wi-Fi disconnected; retrying connection");
  WiFi.disconnect();
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
}

// ======================= GOI API =======================
// Tra ve true neu server tra loi hop le; ket qua nam trong "allow".
// Tra ve false neu mat mang / thieu key / HTTP loi / JSON sai  => caller xu ly fail-closed.
bool askAccessAPI(const String &uid, bool &allowed) {
  lastAuthError = false;

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("API error: Wi-Fi is not connected");
    return false;
  }

  HTTPClient http;
  const String url = String("http://") + serverIp + ":" + SERVER_PORT + ACCESS_PATH;
  if (!http.begin(url)) {
    Serial.println("API error: cannot initialize HTTP client");
    return false;
  }

  http.setConnectTimeout(HTTP_TIMEOUT_MS);
  http.setTimeout(HTTP_TIMEOUT_MS);
  http.addHeader("Content-Type", "application/json");

  StaticJsonDocument<128> request;
  request["uid"] = uid;
  request["device_id"] = DEVICE_ID;
  String requestBody;
  serializeJson(request, requestBody);

  const int statusCode = http.POST(requestBody);
  if (statusCode < 200 || statusCode >= 300) {
    if (statusCode == 401 || statusCode == 403) {
      lastAuthError = true;
      Serial.printf("API error: HTTP %d - API key sai hoac het han. Go lai: key <chuoi moi>\n", statusCode);
    } else {
      // -1: khong ket noi duoc (sai IP/firewall/server chua chay); -11: ket noi duoc nhung server tra loi cham
      Serial.printf("API error: HTTP status %d\n", statusCode);
    }
    if (statusCode > 0) {
      Serial.println(http.getString());
    }
    http.end();
    return false;
  }

  const String responseBody = http.getString();
  http.end();

  StaticJsonDocument<512> response;
  const DeserializationError parseError = deserializeJson(response, responseBody);
  if (parseError || !response["allow"].is<bool>()) {
    Serial.println("API error: invalid JSON or missing boolean 'allow'");
    return false;
  }

  allowed = response["allow"].as<bool>();
  return true;
}

// ======================= HANH DONG =======================
void grantAccess() {
  Serial.println("Ket qua: CHO PHEP");
  digitalWrite(LED_GREEN_PIN, HIGH);
  lockServo.write(SERVO_OPEN_ANGLE);
  delay(SERVO_OPEN_MS);
  lockServo.write(SERVO_CLOSED_ANGLE);
  digitalWrite(LED_GREEN_PIN, LOW);
}

void denyAccess() {  // the sai: den do sang lien + 1 tieng bip dai
  Serial.println("Ket qua: TU CHOI");
  digitalWrite(LED_RED_PIN, HIGH);
  digitalWrite(BUZZER_PIN, HIGH);
  delay(400);
  digitalWrite(BUZZER_PIN, LOW);
  digitalWrite(LED_RED_PIN, LOW);
}

void indicateError() {  // mat mang / server loi: den do nhay nhanh 3 lan + 3 bip ngan, KHONG mo cua
  Serial.println("Ket qua: KHONG XAC DINH (fail-closed, khong mo cua)");
  for (int i = 0; i < 3; ++i) {
    digitalWrite(LED_RED_PIN, HIGH);
    digitalWrite(BUZZER_PIN, HIGH);
    delay(100);
    digitalWrite(LED_RED_PIN, LOW);
    digitalWrite(BUZZER_PIN, LOW);
    delay(100);
  }
}

void indicateAuthError() {  // thieu/sai API key: den do nhay CHAM 2 lan, khong bip (khac loi mang)
  Serial.println("Ket qua: LOI API KEY (fail-closed, khong mo cua)");
  for (int i = 0; i < 2; ++i) {
    digitalWrite(LED_RED_PIN, HIGH);
    delay(400);
    digitalWrite(LED_RED_PIN, LOW);
    delay(400);
  }
}

// ======================= SETUP / LOOP =======================
void setup() {
  Serial.begin(115200);
  delay(200);

  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW);
  pinMode(LED_GREEN_PIN, OUTPUT);
  pinMode(LED_RED_PIN, OUTPUT);
  digitalWrite(LED_GREEN_PIN, LOW);
  digitalWrite(LED_RED_PIN, LOW);

  lockServo.setPeriodHertz(50);
  lockServo.attach(SERVO_PIN, 500, 2400);
  lockServo.write(SERVO_CLOSED_ANGLE);

  SPI.begin(18, 19, 23, RFID_SS_PIN);  // SCK, MISO, MOSI, SS; IRQ khong noi
  reader.PCD_Init();
  Serial.println("MFRC522 ready; tap a card/tag.");

  loadConfig();
  Serial.println("Lenh: show | ip x.x.x.x | key <chuoi> | cfg <ip> <key>");
  connectWiFi();
}

void loop() {
  handleSerialCommand();
  maintainWiFi();

  if (!reader.PICC_IsNewCardPresent() || !reader.PICC_ReadCardSerial()) {
    delay(30);
    return;
  }

  const String uid = uidToUpperHex(reader.uid);
  Serial.print("UID: ");
  Serial.println(uid);

  bool allowed = false;
  if (askAccessAPI(uid, allowed)) {
    if (allowed) {
      grantAccess();
    } else {
      denyAccess();
    }
  } else if (lastAuthError) {
    indicateAuthError();
  } else {
    indicateError();
  }

  reader.PICC_HaltA();
  reader.PCD_StopCrypto1();
  delay(300);
}
