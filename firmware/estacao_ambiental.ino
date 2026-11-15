/*
 * Estação de Monitorização Ambiental de Baixo Custo
 * ESP32 + SDS011 (PM2.5/PM10) + BME680 (T, HR, P, VOC) -> MQTT/TLS
 *
 * Bibliotecas (Gestor de Bibliotecas do Arduino IDE):
 *   - PubSubClient (Nick O'Leary)
 *   - Adafruit BME680 Library (e Adafruit Unified Sensor)
 *   - ArduinoJson (Benoit Blanchon), versão 7.x
 * Placa: "ESP32 Dev Module" (core esp32 da Espressif 2.x ou 3.x)
 */
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_BME680.h>
#include <ArduinoJson.h>
#include <time.h>
#include "config.h"

WiFiClientSecure rede;
PubSubClient mqtt(rede);
Adafruit_BME680 bme;
HardwareSerial sdsSerial(2);

// ---------- SDS011 ----------
// Comando de sono/trabalho: AA B4 06 01 <estado> 00..00 FF FF <CS> AB
void sdsDefinirEstado(bool trabalhar) {
  uint8_t cmd[19] = {0xAA, 0xB4, 0x06, 0x01, (uint8_t)(trabalhar ? 1 : 0),
                     0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0xFF, 0xFF, 0, 0xAB};
  uint16_t soma = 0;
  for (int i = 2; i <= 16; i++) soma += cmd[i];
  cmd[17] = soma & 0xFF;
  sdsSerial.write(cmd, sizeof(cmd));
}

// Trama de resposta (10 bytes): AA C0 PM25L PM25H PM10L PM10H ID1 ID2 CS AB
bool sdsLer(float &pm25, float &pm10, uint32_t timeoutMs = 3000) {
  uint8_t b[10];
  uint32_t t0 = millis();
  while (millis() - t0 < timeoutMs) {
    if (sdsSerial.available() && sdsSerial.read() == 0xAA) {
      b[0] = 0xAA;
      if (sdsSerial.readBytes(&b[1], 9) == 9 && b[1] == 0xC0 && b[9] == 0xAB) {
        uint8_t cs = (b[2] + b[3] + b[4] + b[5] + b[6] + b[7]) & 0xFF;
        if (cs == b[8]) {
          pm25 = ((b[3] << 8) | b[2]) / 10.0f;
          pm10 = ((b[5] << 8) | b[4]) / 10.0f;
          return true;
        }
      }
    }
  }
  return false;
}

// ---------- Rede ----------
void ligarWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  uint32_t t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 20000) delay(250);
}

void ligarMQTT() {
  if (mqtt.connected() || WiFi.status() != WL_CONNECTED) return;
  // Para validar o certificado do broker, usar rede.setCACert(<PEM>);
  rede.setInsecure();  // apenas para testes; em produção usar setCACert()
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setBufferSize(512);
  mqtt.connect(MQTT_CLIENT_ID, MQTT_USER, MQTT_PASSWORD);
}

void sincronizarHora() {
  configTime(0, 0, "pool.ntp.org", "time.google.com");  // UTC
}

// ---------- Programa ----------
void setup() {
  Serial.begin(115200);
  sdsSerial.begin(9600, SERIAL_8N1, SDS_RX_PIN, SDS_TX_PIN);
  Wire.begin(I2C_SDA, I2C_SCL);

  if (!bme.begin(BME_ADDR)) {
    Serial.println("BME680 não encontrado; a reiniciar em 10 s");
    delay(10000);
    ESP.restart();
  }
  bme.setTemperatureOversampling(BME680_OS_8X);
  bme.setHumidityOversampling(BME680_OS_2X);
  bme.setPressureOversampling(BME680_OS_4X);
  bme.setIIRFilterSize(BME680_FILTER_SIZE_3);
  bme.setGasHeater(320, 150);  // 320 °C durante 150 ms

  sdsDefinirEstado(false);
  ligarWiFi();
  sincronizarHora();
}

void loop() {
  uint32_t inicio = millis();

  // 1) Acordar o SDS011 e aguardar estabilização do fluxo de ar
  sdsDefinirEstado(true);
  delay(AQUECIMENTO_S * 1000UL);

  // 2) Média de N leituras do SDS011
  float s25 = 0, s10 = 0, p25, p10;
  int ok = 0;
  for (int i = 0; i < N_AMOSTRAS_PM; i++) {
    if (sdsLer(p25, p10)) { s25 += p25; s10 += p10; ok++; }
  }
  sdsDefinirEstado(false);

  // 3) BME680
  bool bmeOk = bme.performReading();

  // 4) Publicar
  ligarWiFi();
  ligarMQTT();
  if (mqtt.connected() && (ok > 0 || bmeOk)) {
    JsonDocument doc;
    time_t agora = time(nullptr);
    if (agora > 1700000000) doc["ts"] = (uint32_t)agora;  // só se NTP sincronizado
    if (ok > 0) {
      float m25 = s25 / ok, m10 = s10 / ok;
      doc["pm25_raw"] = round(m25 * 10) / 10.0;
      doc["pm10_raw"] = round(m10 * 10) / 10.0;
      doc["pm25"] = round((CAL_PM25_A * m25 + CAL_PM25_B) * 10) / 10.0;
      doc["pm10"] = round((CAL_PM10_A * m10 + CAL_PM10_B) * 10) / 10.0;
    }
    if (bmeOk) {
      doc["temperatura"] = round((bme.temperature + BME_TEMP_OFFSET) * 100) / 100.0;
      doc["humidade"]    = round(bme.humidity * 10) / 10.0;
      doc["pressao"]     = round(bme.pressure / 100.0 * 10) / 10.0;  // hPa
      doc["gas_kohm"]    = round(bme.gas_resistance / 1000.0 * 10) / 10.0;
    }
    doc["rssi"] = WiFi.RSSI();
    char buf[320];
    size_t n = serializeJson(doc, buf);
    mqtt.publish(MQTT_TOPIC, (const uint8_t *)buf, n, false);
    mqtt.loop();
    Serial.println(buf);
  } else {
    Serial.println("Sem ligação MQTT ou sem dados; nova tentativa no próximo ciclo");
  }

  // 5) Aguardar até completar o período
  uint32_t gasto = millis() - inicio;
  if (gasto < PERIODO_S * 1000UL) delay(PERIODO_S * 1000UL - gasto);
}
