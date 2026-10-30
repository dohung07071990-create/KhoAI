/* KhoAI - AI Thinker ESP32-CAM: web page, /capture still image, :81/stream MJPEG.
   Fill in Wi-Fi credentials before flashing. */
#include "esp_camera.h"
#include <WiFi.h>
#include "esp_http_server.h"
const char *WIFI_SSID = "YOUR_WIFI_SSID";
const char *WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
#define PWDN_GPIO_NUM 32
#define RESET_GPIO_NUM -1
#define XCLK_GPIO_NUM 0
#define SIOD_GPIO_NUM 26
#define SIOC_GPIO_NUM 27
#define Y9_GPIO_NUM 35
#define Y8_GPIO_NUM 34
#define Y7_GPIO_NUM 39
#define Y6_GPIO_NUM 36
#define Y5_GPIO_NUM 21
#define Y4_GPIO_NUM 19
#define Y3_GPIO_NUM 18
#define Y2_GPIO_NUM 5
#define VSYNC_GPIO_NUM 25
#define HREF_GPIO_NUM 23
#define PCLK_GPIO_NUM 22
static httpd_handle_t pageServer=nullptr, streamServer=nullptr;
static const char *STREAM_CONTENT_TYPE="multipart/x-mixed-replace;boundary=frame";
static const char *STREAM_BOUNDARY="\r\n--frame\r\n";
static const char *STREAM_PART="Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";
static esp_err_t indexHandler(httpd_req_t *req){String host=WiFi.localIP().toString();String html="<!doctype html><html><head><meta name='viewport' content='width=device-width,initial-scale=1'><title>KhoAI ESP32-CAM</title></head><body><h2>KhoAI ESP32-CAM</h2><img src='http://"+host+":81/stream' style='width:100%;max-width:800px'></body></html>";httpd_resp_set_type(req,"text/html; charset=utf-8");return httpd_resp_send(req,html.c_str(),html.length());}
static esp_err_t captureHandler(httpd_req_t *req){camera_fb_t *old=esp_camera_fb_get();if(old)esp_camera_fb_return(old);camera_fb_t *frame=esp_camera_fb_get();if(!frame){httpd_resp_send_500(req);return ESP_FAIL;}httpd_resp_set_type(req,"image/jpeg");httpd_resp_set_hdr(req,"Access-Control-Allow-Origin","*");esp_err_t result=httpd_resp_send(req,(const char*)frame->buf,frame->len);esp_camera_fb_return(frame);return result;}
static esp_err_t streamHandler(httpd_req_t *req){esp_err_t result=httpd_resp_set_type(req,STREAM_CONTENT_TYPE);if(result!=ESP_OK)return result;httpd_resp_set_hdr(req,"Access-Control-Allow-Origin","*");while(true){camera_fb_t *frame=esp_camera_fb_get();if(!frame)return ESP_FAIL;char header[64];size_t n=snprintf(header,sizeof(header),STREAM_PART,(unsigned int)frame->len);result=httpd_resp_send_chunk(req,STREAM_BOUNDARY,strlen(STREAM_BOUNDARY));if(result==ESP_OK)result=httpd_resp_send_chunk(req,header,n);if(result==ESP_OK)result=httpd_resp_send_chunk(req,(const char*)frame->buf,frame->len);esp_camera_fb_return(frame);if(result!=ESP_OK)break;}httpd_resp_send_chunk(req,nullptr,0);return result;}
void startWebServers(){httpd_config_t pc=HTTPD_DEFAULT_CONFIG();pc.server_port=80;pc.ctrl_port=32768;httpd_uri_t root={};root.uri="/";root.method=HTTP_GET;root.handler=indexHandler;httpd_uri_t cap={};cap.uri="/capture";cap.method=HTTP_GET;cap.handler=captureHandler;if(httpd_start(&pageServer,&pc)==ESP_OK){httpd_register_uri_handler(pageServer,&root);httpd_register_uri_handler(pageServer,&cap);}else Serial.println("Could not start page server");httpd_config_t sc=HTTPD_DEFAULT_CONFIG();sc.server_port=81;sc.ctrl_port=32769;sc.max_uri_handlers=2;httpd_uri_t stream={};stream.uri="/stream";stream.method=HTTP_GET;stream.handler=streamHandler;if(httpd_start(&streamServer,&sc)==ESP_OK)httpd_register_uri_handler(streamServer,&stream);else Serial.println("Could not start stream server");}
void setup(){Serial.begin(115200);Serial.setDebugOutput(false);camera_config_t c={};c.ledc_channel=LEDC_CHANNEL_0;c.ledc_timer=LEDC_TIMER_0;c.pin_d0=Y2_GPIO_NUM;c.pin_d1=Y3_GPIO_NUM;c.pin_d2=Y4_GPIO_NUM;c.pin_d3=Y5_GPIO_NUM;c.pin_d4=Y6_GPIO_NUM;c.pin_d5=Y7_GPIO_NUM;c.pin_d6=Y8_GPIO_NUM;c.pin_d7=Y9_GPIO_NUM;c.pin_xclk=XCLK_GPIO_NUM;c.pin_pclk=PCLK_GPIO_NUM;c.pin_vsync=VSYNC_GPIO_NUM;c.pin_href=HREF_GPIO_NUM;c.pin_sccb_sda=SIOD_GPIO_NUM;c.pin_sccb_scl=SIOC_GPIO_NUM;c.pin_pwdn=PWDN_GPIO_NUM;c.pin_reset=RESET_GPIO_NUM;c.xclk_freq_hz=20000000;c.pixel_format=PIXFORMAT_JPEG;c.frame_size=FRAMESIZE_QVGA;c.jpeg_quality=15;c.fb_count=1;c.fb_location=psramFound()?CAMERA_FB_IN_PSRAM:CAMERA_FB_IN_DRAM;c.grab_mode=CAMERA_GRAB_WHEN_EMPTY;esp_err_t result=esp_camera_init(&c);if(result!=ESP_OK){Serial.printf("Camera init failed: 0x%x\n",result);delay(2000);ESP.restart();}WiFi.mode(WIFI_STA);WiFi.setSleep(false);WiFi.begin(WIFI_SSID,WIFI_PASSWORD);Serial.print("Connecting to Wi-Fi");uint32_t started=millis();while(WiFi.status()!=WL_CONNECTED){if(millis()-started>20000){Serial.println("\nWi-Fi timeout; restarting");ESP.restart();}delay(500);Serial.print('.');}Serial.println();Serial.print("ESP32-CAM IP: ");Serial.println(WiFi.localIP());startWebServers();Serial.println("Page: http://<IP>/ ; Capture: http://<IP>/capture ; MJPEG: http://<IP>:81/stream");}
void loop(){static uint32_t lostSince=0;if(WiFi.status()!=WL_CONNECTED){if(!lostSince)lostSince=millis();if(millis()-lostSince>30000){Serial.println("Wi-Fi lost over 30s, restarting");ESP.restart();}}else lostSince=0;delay(1000);}
