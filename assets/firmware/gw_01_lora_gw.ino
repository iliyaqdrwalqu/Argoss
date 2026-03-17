// ArgosUniversal LoRa Gateway — автогенерация
#include <SPI.h>
#include <LoRa.h>
#include <WiFi.h>
#include <PubSubClient.h>

#define LORA_FREQ    433000000
#define LORA_SS      5
#define LORA_RST     14
#define LORA_DIO0    2
#define MQTT_TOPIC   "argos/lora"

void setup() {
  Serial.begin(115200);
  LoRa.setPins(LORA_SS, LORA_RST, LORA_DIO0);
  if (!LoRa.begin(LORA_FREQ)) while(true);
  // WiFi + MQTT init here
  Serial.println("ArgosGW LoRa ready @ 433.0MHz");
}

void loop() {
  int pktSize = LoRa.parsePacket();
  if (pktSize) {
    String data = "";
    while (LoRa.available()) data += (char)LoRa.read();
    // publish to MQTT
    Serial.println("RX: " + data);
  }
}
