#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <SPI.h>
#include <MFRC522.h>
#include <ESP32Servo.h>

// --- Cấu hình mạng: thay placeholder bằng thông tin mạng/server của bạn ---
const char *WIFI_SSID = "YOUR_WIFI_SSID";
const char *WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
const char *SERVER_IP = "192.168.1.100";  // IP máy chạy API trong cùng mạng
const uint16_t SERVER_PORT = 3000;
const char *ACCESS_PATH = "/api/access/check";

// ESP32 VSPI mặc định: SS/SDA=GPIO5, SCK=18, MOSI=23, MISO=19.
constexpr uint8_t RFID_SS_PIN = 5;
constexpr uint8_t RFID_RST_PIN = 22;
constexpr uint8_t SERVO_PIN = 13;
constexpr uint8_t BUZZER_PIN = 27;  // Còi chủ động, kích mức HIGH
constexpr int SERVO_CLOSED_ANGLE = 0;
constexpr int SERVO_OPEN_ANGLE = 90;
constexpr unsigned long SERVO_OPEN_MS = 2000;
constexpr unsigned long WIFI_CONNECT_TIMEOUT_MS = 10000;
constexpr unsigned long WIFI_RETRY_INTERVAL_MS = 10000;
unsigned long lastWiFiAttemptMs = 0;

MFRC522 reader(RFID_SS_PIN, RFID_RST_PIN);
Servo lockServo;

String uidToUpperHex(const MFRC522::Uid &uid) {
  String result;
  result.reserve(uid.size * 2);
  char byteText[3];
  for (byte i = 0; i < uid.size; ++i) {
    snprintf(byteText, sizeof(byteText), "%02X", uid.uidByte[i]);
    result += byteText;
  }
  return result;
}

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

bool askAccessAPI(const String &uid, bool &allowed) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("API error: Wi-Fi is not connected");
    return false;
  }

  HTTPClient http;
  const String url = String("http://") + SERVER_IP + ":" + SERVER_PORT + ACCESS_PATH;
  if (!http.begin(url)) {
    Serial.println("API error: cannot initialize HTTP client");
    return false;
  }

  http.addHeader("Content-Type", "application/json");
  StaticJsonDocument<96> request;
  request["uid"] = uid;
  String requestBody;
  serializeJson(request, requestBody);

  const int statusCode = http.POST(requestBody);
  if (statusCode < 200 || statusCode >= 300) {
    Serial.printf("API error: HTTP status %d\n", statusCode);
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
  if (parseError || !response["allowed"].is<bool>()) {
    Serial.println("API error: invalid JSON or missing boolean 'allowed'");
    return false;
  }

  allowed = response["allowed"].as<bool>();
  return true;
}

void grantAccess() {
  Serial.println("Ket qua: CHO PHEP");
  lockServo.write(SERVO_OPEN_ANGLE);
  delay(SERVO_OPEN_MS);
  lockServo.write(SERVO_CLOSED_ANGLE);
}

void denyAccess() {
  Serial.println("Ket qua: TU CHOI");
  digitalWrite(BUZZER_PIN, HIGH);
  delay(150);
  digitalWrite(BUZZER_PIN, LOW);
}

void setup() {
  Serial.begin(115200);
  delay(200);

  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW);
  lockServo.setPeriodHertz(50);
  lockServo.attach(SERVO_PIN, 500, 2400);
  lockServo.write(SERVO_CLOSED_ANGLE);

  SPI.begin(18, 19, 23, RFID_SS_PIN);  // SCK, MISO, MOSI, SS; IRQ không nối
  reader.PCD_Init();
  Serial.println("MFRC522 ready; tap a card/tag.");
  connectWiFi();
}

void loop() {
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
  } else {
    // Lỗi mạng/API được xử lý theo hướng fail-closed: không mở servo.
    Serial.println("Ket qua: KHONG XAC DINH (fail-closed, khong mo cua)");
  }

  reader.PICC_HaltA();
  reader.PCD_StopCrypto1();
  delay(300);
}
