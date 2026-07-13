#include "esp_camera.h"

// =======================
// ESP32-CAM AI THINKER
// =======================
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

#define SERIAL_BAUDRATE 921600

void sendFrame(camera_fb_t *fb) {
  if (!fb) {
    return;
  }

  uint32_t imageSize = fb->len;

  // Protocolo:
  // START: 0xAA 0x55
  // SIZE : uint32 little-endian
  // JPEG : bytes
  // END  : 0x55 0xAA

  Serial.write(0xAA);
  Serial.write(0x55);

  Serial.write((uint8_t *)&imageSize, 4);

  Serial.write(fb->buf, fb->len);

  Serial.write(0x55);
  Serial.write(0xAA);

  Serial.flush();
}

void setup() {

  Serial.begin(SERIAL_BAUDRATE);
  delay(1000);

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

  config.xclk_freq_hz = 10000000;
  config.pixel_format = PIXFORMAT_JPEG;

  // Resolução baixa para aumentar FPS na UART
  config.frame_size = FRAMESIZE_QQVGA;   // 160x120
  config.jpeg_quality = 18;
  config.fb_count = 1;

  if (psramFound()) {
    config.fb_location = CAMERA_FB_IN_PSRAM;
  } else {
    config.fb_location = CAMERA_FB_IN_DRAM;
  }

  config.grab_mode = CAMERA_GRAB_WHEN_EMPTY;

  esp_err_t err = esp_camera_init(&config);

  if (err != ESP_OK) {
    while (true) {
      delay(1000);
    }
  }

  sensor_t *s = esp_camera_sensor_get();

  s->set_framesize(s, FRAMESIZE_QQVGA);
  s->set_quality(s, 18);
  s->set_brightness(s, 0);
  s->set_contrast(s, 0);
  s->set_saturation(s, 0);

  delay(1000);
}

void loop() {

  camera_fb_t *fb = esp_camera_fb_get();

  if (fb != NULL) {

    sendFrame(fb);

    esp_camera_fb_return(fb);
  }

  // Ajuste conforme desempenho
  delay(150);
}