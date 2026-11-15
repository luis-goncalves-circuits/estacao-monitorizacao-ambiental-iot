// config.h — configuração da estação (NÃO publicar com credenciais reais)
#pragma once

#define WIFI_SSID        "A_MINHA_REDE"
#define WIFI_PASSWORD    "A_MINHA_PALAVRA_PASSE"

#define MQTT_HOST        "mqtt.exemplo.pt"   // IP ou nome do broker
#define MQTT_PORT        8883                // TLS
#define MQTT_USER        "estacao01"
#define MQTT_PASSWORD    "PALAVRA_PASSE_MQTT"
#define MQTT_TOPIC       "amora/setubal/estacao01/medicoes"
#define MQTT_CLIENT_ID   "estacao01"

// Pinos
#define SDS_RX_PIN       16   // ESP32 RX2  <- TX do SDS011
#define SDS_TX_PIN       17   // ESP32 TX2  -> RX do SDS011
#define I2C_SDA          21
#define I2C_SCL          22
#define BME_ADDR         0x77 // 0x76 se SDO ligado a GND

// Temporização
#define PERIODO_S        60   // intervalo entre publicações
#define AQUECIMENTO_S    30   // tempo de ventilação do SDS011 antes de ler
#define N_AMOSTRAS_PM    5    // leituras do SDS011 promediadas por ciclo

// Coeficientes de calibração (PM_corr = A * PM_med + B).
// Valores por defeito = sem correção; substituir após a calibração (calibracao.py).
#define CAL_PM25_A       1.000f
#define CAL_PM25_B       0.000f
#define CAL_PM10_A       1.000f
#define CAL_PM10_B       0.000f

// Compensação da temperatura do BME680 (aquecimento próprio da placa), em °C
#define BME_TEMP_OFFSET  0.0f
