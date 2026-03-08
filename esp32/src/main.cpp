#include <WiFi.h>
#include <PubSubClient.h>
#include <Adafruit_NeoPixel.h>

#define LED_PIN    13
#define LED_COUNT  16
#define MY_BOX_ID  1   

const char* ssid = "KreMa445";
const char* pass = "Dahoam445";

const char* mqtt_host = "10.0.0.49";  
const int   mqtt_port = 1883;
const char* mqtt_topic_final = "rescuesys/box/final";

WiFiClient espClient;
PubSubClient client(espClient);
Adafruit_NeoPixel strip(LED_COUNT, LED_PIN, NEO_GRBW + NEO_KHZ800);

void setColor(uint8_t r, uint8_t g, uint8_t b, uint8_t w=0) {
  for (int i=0; i<LED_COUNT; i++) strip.setPixelColor(i, strip.Color(r,g,b,w));
  strip.show();
}

bool parseCycleStatus(const char* s, int &cycle, int &status) {
  const char* comma = strchr(s, ',');
  if (!comma) return false;

  cycle = atoi(s);
  status = atoi(comma + 1);
  return true;
}

void callback(char* topic, byte* payload, unsigned int length) {
  char msg[32];
  if (length >= sizeof(msg)) length = sizeof(msg)-1;
  memcpy(msg, payload, length);
  msg[length] = 0;

  int cycle = -1, status = -1;
  if (!parseCycleStatus(msg, cycle, status)) return;

  if (cycle != MY_BOX_ID) return;

  if      (status == 0) setColor(0,255,0,0);      
  else if (status == 1) setColor(255,150,0,0);    
  else if (status == 2) setColor(255,0,0,0);      
}

void reconnect() {
  while (!client.connected()) {
    String clientId = "box-" + String(MY_BOX_ID);
    if (client.connect(clientId.c_str())) {
      client.subscribe(mqtt_topic_final, 1);
    } else {
      delay(1000);
    }
  }
}

void setup() {
  strip.begin();
  strip.setBrightness(50);
  strip.show();
  setColor(0,0,0,0);

  WiFi.begin(ssid, pass);
  while (WiFi.status() != WL_CONNECTED) delay(250);

  client.setServer(mqtt_host, mqtt_port);
  client.setCallback(callback);
}

void loop() {
  if (!client.connected()) reconnect();
  client.loop();
}
