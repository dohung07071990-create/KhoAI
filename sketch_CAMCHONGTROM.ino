#include "esp_camera.h"
#include <WiFi.h>
#include "esp_http_server.h"

// --- Cấu hình mạng: điền WiFi hotspot (phải là 2.4 GHz) ---
const char *WIFI_SSID = "GiapHuong";
const char *WIFI_PASSWORD = "GIAPHUONG262";

// Pin map module AI Thinker ESP32-CAM.
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27
#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

static httpd_handle_t pageServer = nullptr;
static httpd_handle_t streamServer = nullptr;
static const char *STREAM_CONTENT_TYPE = "multipart/x-mixed-replace;boundary=frame";
static const char *STREAM_BOUNDARY = "\r\n--frame\r\n";
static const char *STREAM_PART = "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

static esp_err_t indexHandler(httpd_req_t *request) {
  static const char page[] =
      "<!doctype html><html><head><meta name='viewport' content='width=device-width,initial-scale=1'>"
      "<title>ESP32-CAM</title></head><body><h2>ESP32-CAM MJPEG</h2>"
      "<img src='http://";
  const String host = WiFi.localIP().toString();
  String html = String(page) + host + ":81/stream' style='width:100%;max-width:800px'>"
                "</body></html>";
  httpd_resp_set_type(request, "text/html; charset=utf-8");
  return httpd_resp_send(request, html.c_str(), html.length());
}

// Ảnh tĩnh: server gọi http://<IP>/capture khi có sự kiện quẹt thẻ
static esp_err_t captureHandler(httpd_req_t *request) {
  // Bỏ khung cũ trong buffer, lấy khung mới nhất
  camera_fb_t *old = esp_camera_fb_get();
  if (old) esp_camera_fb_return(old);

  camera_fb_t *frame = esp_camera_fb_get();
  if (frame == nullptr) {
    httpd_resp_send_500(request);
    return ESP_FAIL;
  }
  httpd_resp_set_type(request, "image/jpeg");
  httpd_resp_set_hdr(request, "Access-Control-Allow-Origin", "*");
  const esp_err_t result = httpd_resp_send(request, reinterpret_cast<const char *>(frame->buf), frame->len);
  esp_camera_fb_return(frame);
  return result;
}

static esp_err_t streamHandler(httpd_req_t *request) {
  esp_err_t result = httpd_resp_set_type(request, STREAM_CONTENT_TYPE);
  if (result != ESP_OK) {
    return result;
  }
  httpd_resp_set_hdr(request, "Access-Control-Allow-Origin", "*");

  while (true) {
    camera_fb_t *frame = esp_camera_fb_get();
    if (frame == nullptr) {
      Serial.println("Camera capture failed");
      return ESP_FAIL;
    }

    char partHeader[64];
    const size_t headerLength = snprintf(partHeader, sizeof(partHeader), STREAM_PART,
                                         static_cast<unsigned int>(frame->len));
    result = httpd_resp_send_chunk(request, STREAM_BOUNDARY, strlen(STREAM_BOUNDARY));
    if (result == ESP_OK) {
      result = httpd_resp_send_chunk(request, partHeader, headerLength);
    }
    if (result == ESP_OK) {
      result = httpd_resp_send_chunk(request, reinterpret_cast<const char *>(frame->buf), frame->len);
    }
    esp_camera_fb_return(frame);

    if (result != ESP_OK) {
      break;  // Client ngắt kết nối.
    }
  }
  httpd_resp_send_chunk(request, nullptr, 0);
  return result;
}

void startWebServers() {
  httpd_config_t pageConfig = HTTPD_DEFAULT_CONFIG();
  pageConfig.server_port = 80;
  pageConfig.ctrl_port = 32768;

  httpd_uri_t indexUri = {};
  indexUri.uri = "/";
  indexUri.method = HTTP_GET;
  indexUri.handler = indexHandler;
  indexUri.user_ctx = nullptr;

  httpd_uri_t captureUri = {};
  captureUri.uri = "/capture";
  captureUri.method = HTTP_GET;
  captureUri.handler = captureHandler;
  captureUri.user_ctx = nullptr;

  if (httpd_start(&pageServer, &pageConfig) == ESP_OK) {
    httpd_register_uri_handler(pageServer, &indexUri);
    httpd_register_uri_handler(pageServer, &captureUri);
  } else {
    Serial.println("Could not start page server on port 80");
  }

  httpd_config_t streamConfig = HTTPD_DEFAULT_CONFIG();
  streamConfig.server_port = 81;
  streamConfig.ctrl_port = 32769;
  streamConfig.max_uri_handlers = 2;

  httpd_uri_t streamUri = {};
  streamUri.uri = "/stream";
  streamUri.method = HTTP_GET;
  streamUri.handler = streamHandler;
  streamUri.user_ctx = nullptr;

  if (httpd_start(&streamServer, &streamConfig) == ESP_OK) {
    httpd_register_uri_handler(streamServer, &streamUri);
  } else {
    Serial.println("Could not start MJPEG server on port 81");
  }
}

void setup() {
  Serial.begin(115200);
  Serial.setDebugOutput(false);

  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;

    
  if (psramFound()) {
    Serial.println("PSRAM found");
  } else {
    Serial.println("PSRAM not found");
  }

  // Cau hinh nhe de kiem tra loi cap phat bo nho
  config.frame_size = FRAMESIZE_QVGA;  // 320x240
  config.jpeg_quality = 15;
  config.fb_count = 1;
  config.fb_location = CAMERA_FB_IN_DRAM;
  config.grab_mode = CAMERA_GRAB_WHEN_EMPTY;


  const esp_err_t cameraResult = esp_camera_init(&config);
  if (cameraResult != ESP_OK) {
    Serial.printf("Camera init failed: 0x%x\n", cameraResult);
    delay(2000);
    ESP.restart();
  }

  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);  // tránh cam bị trễ do WiFi ngủ
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("Connecting to Wi-Fi");
  const uint32_t startMs = millis();
  while (WiFi.status() != WL_CONNECTED) {
    if (millis() - startMs > 20000) {
      Serial.println("\nWiFi timeout, restarting");
      ESP.restart();
    }
    delay(500);
    Serial.print('.');
  }
  Serial.println();
  Serial.print("ESP32-CAM IP: ");
  Serial.println(WiFi.localIP());

  startWebServers();
  Serial.println("Page:    http://<ESP32-CAM-IP>/");
  Serial.println("Capture: http://<ESP32-CAM-IP>/capture");
  Serial.println("MJPEG:   http://<ESP32-CAM-IP>:81/stream");
}

void loop() {
  static uint32_t lostSince = 0;
  if (WiFi.status() != WL_CONNECTED) {
    if (lostSince == 0) lostSince = millis();
    if (millis() - lostSince > 30000) {
      Serial.println("WiFi lost over 30s, restarting");
      ESP.restart();
    }
  } else {
    lostSince = 0;
  }
  delay(1000);
}