/* KhoAI - ESP32 + RC522 + Servo + buzzer + status LEDs
   Libraries: MFRC522, ArduinoJson v6/v7, ESP32Servo, Preferences
   Serial commands: show | ip <server-ip> | key <api-key> | cfg <ip> <key>
   Fail-closed: network/API/JSON errors never open the lock.
*/
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <SPI.h>
#include <MFRC522.h>
#include <ESP32Servo.h>
#include <Preferences.h>

const char *WIFI_SSID = "YOUR_WIFI_SSID";
const char *WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
String serverIp = "192.168.1.50"; // Set to the PC running KhoAI; can be changed via Serial.
String apiKey = "";              // Optional; if KHOAI_API_KEY is configured on server, set this.
const uint16_t SERVER_PORT = 3000; // Default KhoAI port; change if your server uses another port.
const char *ACCESS_PATH = "/api/rfid/scan";
const char *API_KEY_HEADER = "X-API-Key";
const char *DEVICE_ID = "gate01";
constexpr uint16_t HTTP_TIMEOUT_MS = 3000;
constexpr unsigned long WIFI_CONNECT_TIMEOUT_MS = 10000;
constexpr unsigned long WIFI_RETRY_INTERVAL_MS = 10000;
constexpr uint8_t RFID_SS_PIN = 5, RFID_RST_PIN = 22, SERVO_PIN = 13;
constexpr uint8_t BUZZER_PIN = 27, LED_GREEN_PIN = 25, LED_RED_PIN = 26;
constexpr int SERVO_CLOSED_ANGLE = 0, SERVO_OPEN_ANGLE = 90;
constexpr unsigned long SERVO_OPEN_MS = 2000;
unsigned long lastWiFiAttemptMs = 0;
bool lastAuthError = false;
MFRC522 reader(RFID_SS_PIN, RFID_RST_PIN);
Servo lockServo;
Preferences prefs;

String uidToUpperHex(const MFRC522::Uid &uid) {
  String result; result.reserve(uid.size * 2); char byteText[3];
  for (byte i = 0; i < uid.size; ++i) { snprintf(byteText, sizeof(byteText), "%02X", uid.uidByte[i]); result += byteText; }
  return result;
}
String maskKey(const String &key) { if (!key.length()) return "(chua dat)"; if (key.length() <= 4) return "**"; return "**" + key.substring(key.length()-4); }
void printConfig() { Serial.println("Server IP: " + serverIp); Serial.println("Server port: " + String(SERVER_PORT)); Serial.println("API key: " + maskKey(apiKey)); }
void loadConfig() { prefs.begin("cfg", false); serverIp=prefs.getString("srv_ip",serverIp); apiKey=prefs.getString("api_key",""); prefs.end(); printConfig(); }
bool setServerIp(String v) { v.trim(); IPAddress test; if (!test.fromString(v)) { Serial.println("IP khong hop le."); return false; } prefs.begin("cfg",false); prefs.putString("srv_ip",v); prefs.end(); serverIp=v; Serial.println("Da luu IP: "+serverIp); return true; }
bool setApiKey(String v) { v.trim(); if (!v.length()) { Serial.println("Key trong."); return false; } prefs.begin("cfg",false); prefs.putString("api_key",v); prefs.end(); apiKey=v; Serial.println("Da luu API key: "+maskKey(apiKey)); return true; }
void handleSerialCommand() {
  if (!Serial.available()) return; String line=Serial.readStringUntil('\n'); line.trim(); if (!line.length()) return;
  if (line=="show" || line=="ip" || line=="key") printConfig();
  else if (line.startsWith("ip ")) setServerIp(line.substring(3));
  else if (line.startsWith("key ")) setApiKey(line.substring(4));
  else if (line.startsWith("cfg ")) { String rest=line.substring(4); rest.trim(); int sp=rest.indexOf(' '); if(sp<0){Serial.println("Cu phap: cfg <ip> <key>");return;} if(setServerIp(rest.substring(0,sp))) setApiKey(rest.substring(sp+1)); }
  else Serial.println("Lenh: show | ip x.x.x.x | key <chuoi> | cfg <ip> <key>");
}
void connectWiFi() {
  WiFi.mode(WIFI_STA); WiFi.begin(WIFI_SSID,WIFI_PASSWORD); unsigned long started=millis(); Serial.print("Dang ket noi Wi-Fi");
  while(WiFi.status()!=WL_CONNECTED && millis()-started<WIFI_CONNECT_TIMEOUT_MS){delay(500);Serial.print('.');} Serial.println();
  if(WiFi.status()==WL_CONNECTED){Serial.print("Wi-Fi connected; ESP32 IP: ");Serial.println(WiFi.localIP());} else Serial.println("Wi-Fi timeout; access remains fail-closed."); lastWiFiAttemptMs=millis();
}
void maintainWiFi(){ if(WiFi.status()==WL_CONNECTED || millis()-lastWiFiAttemptMs<WIFI_RETRY_INTERVAL_MS)return; lastWiFiAttemptMs=millis(); Serial.println("Wi-Fi disconnected; retrying"); WiFi.disconnect(); WiFi.begin(WIFI_SSID,WIFI_PASSWORD); }
bool askAccessAPI(const String &uid, bool &allowed) {
  lastAuthError=false; if(WiFi.status()!=WL_CONNECTED){Serial.println("API error: Wi-Fi disconnected");return false;}
  HTTPClient http; String url=String("http://")+serverIp+":"+SERVER_PORT+ACCESS_PATH;
  if(!http.begin(url)){Serial.println("Cannot initialize HTTP");return false;} http.setConnectTimeout(HTTP_TIMEOUT_MS); http.setTimeout(HTTP_TIMEOUT_MS);
  http.addHeader("Content-Type","application/json"); if(apiKey.length()) http.addHeader(API_KEY_HEADER,apiKey);
  StaticJsonDocument<128> request; request["uid"]=uid; request["device_id"]=DEVICE_ID; String body; serializeJson(request,body);
  int code=http.POST(body); if(code<200 || code>=300){if(code==401 || code==403){lastAuthError=true;Serial.printf("API key rejected (HTTP %d); enter: key <new-key>\n",code);}else Serial.printf("API error: HTTP %d\n",code); if(code>0)Serial.println(http.getString());http.end();return false;}
  String responseBody=http.getString();http.end();StaticJsonDocument<512> response;auto err=deserializeJson(response,responseBody);
  if(err || !response["allow"].is<bool>()){Serial.println("Invalid JSON or missing boolean allow");return false;} allowed=response["allow"].as<bool>();return true;
}
void grantAccess(){Serial.println("Ket qua: CHO PHEP");digitalWrite(LED_GREEN_PIN,HIGH);lockServo.write(SERVO_OPEN_ANGLE);delay(SERVO_OPEN_MS);lockServo.write(SERVO_CLOSED_ANGLE);digitalWrite(LED_GREEN_PIN,LOW);}
void denyAccess(){Serial.println("Ket qua: TU CHOI");digitalWrite(LED_RED_PIN,HIGH);for(int i=0;i<4;i++){digitalWrite(BUZZER_PIN,HIGH);delay(150);digitalWrite(BUZZER_PIN,LOW);delay(150);}digitalWrite(LED_RED_PIN,LOW);}
void indicateError(){Serial.println("KHONG XAC DINH - fail-closed");for(int i=0;i<3;i++){digitalWrite(LED_RED_PIN,HIGH);digitalWrite(BUZZER_PIN,HIGH);delay(100);digitalWrite(LED_RED_PIN,LOW);digitalWrite(BUZZER_PIN,LOW);delay(100);}}
void indicateAuthError(){Serial.println("LOI API KEY - fail-closed");for(int i=0;i<2;i++){digitalWrite(LED_RED_PIN,HIGH);delay(400);digitalWrite(LED_RED_PIN,LOW);delay(400);}}
void setup(){
  Serial.begin(115200);delay(200);pinMode(BUZZER_PIN,OUTPUT);pinMode(LED_GREEN_PIN,OUTPUT);pinMode(LED_RED_PIN,OUTPUT);digitalWrite(BUZZER_PIN,LOW);digitalWrite(LED_GREEN_PIN,LOW);digitalWrite(LED_RED_PIN,LOW);
  lockServo.setPeriodHertz(50);lockServo.attach(SERVO_PIN,500,2400);lockServo.write(SERVO_CLOSED_ANGLE);SPI.begin(18,19,23,RFID_SS_PIN);reader.PCD_Init();Serial.println("MFRC522 ready; tap card.");loadConfig();Serial.println("Commands: show | ip <ip> | key <key> | cfg <ip> <key>");connectWiFi();
}
void loop(){handleSerialCommand();maintainWiFi();if(!reader.PICC_IsNewCardPresent()||!reader.PICC_ReadCardSerial()){delay(30);return;}String uid=uidToUpperHex(reader.uid);Serial.println("UID: "+uid);bool allowed=false;if(askAccessAPI(uid,allowed)){if(allowed)grantAccess();else denyAccess();}else if(lastAuthError)indicateAuthError();else indicateError();reader.PICC_HaltA();reader.PCD_StopCrypto1();delay(300);}
