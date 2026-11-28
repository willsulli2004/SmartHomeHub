#define LIDAR_RX 21   // from C1 TX
#define LIDAR_TX 47   // to C1 RX
#define LIDAR_EN 38

HardwareSerial &lidar = Serial1;

float bins[360], lastBins[360];
int pts = 0, lastPts = 0, scans = 0;

void sendCmd(uint8_t cmd) {
  uint8_t p[2] = {0xA5, cmd};
  lidar.write(p, 2);
}

bool readBytes(uint8_t *buf, size_t n, uint32_t timeout) {
  uint32_t start = millis();
  size_t i = 0;
  while (i < n && millis() - start < timeout)
    if (lidar.available()) buf[i++] = lidar.read();
  return i == n;
}

// response descriptor is A5 5A + 5 bytes
bool readDescriptor() {
  uint8_t d[6];
  uint32_t start = millis();
  while (millis() - start < 1000) {
    if (lidar.available() && lidar.read() == 0xA5)
      if (readBytes(d, 6, 200) && d[0] == 0x5A) return true;
  }
  return false;
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  pinMode(LIDAR_EN, OUTPUT);
  digitalWrite(LIDAR_EN, HIGH);
  Serial.println("LiDAR power on");
  delay(2000);

  lidar.setRxBufferSize(8192);
  lidar.begin(460800, SERIAL_8N1, LIDAR_RX, LIDAR_TX);

  sendCmd(0x25);   // stop, in case it was already scanning
  delay(50);
  while (lidar.available()) lidar.read();

  sendCmd(0x50);   // get info
  uint8_t info[20];
  if (readDescriptor() && readBytes(info, 20, 500)) {
    Serial.printf("Model 0x%02X  firmware %d.%02d  hardware %d\n", info[0], info[2], info[1], info[3]);
  } else {
    Serial.println("No response: check power, TX/RX swap, baud");
    while (true) delay(1000);
  }

  sendCmd(0x52);   // get health
  uint8_t health[3];
  if (readDescriptor() && readBytes(health, 3, 500))
    Serial.printf("Health: %s (error code %d)\n",
                  health[0] == 0 ? "OK" : health[0] == 1 ? "WARNING" : "ERROR",
                  health[1] | (health[2] << 8));

  sendCmd(0x20);   // start scan
  if (!readDescriptor()) Serial.println("Scan didn't start");
  Serial.println("Scanning...\n");
}

void processNode(uint8_t *n) {
  bool newScan = n[0] & 1;
  float angle = ((n[1] >> 1) | (n[2] << 7)) / 64.0;
  float dist = (n[3] | (n[4] << 8)) / 4.0;   // mm, 0 = no return

  if (newScan) {
    memcpy(lastBins, bins, sizeof(bins));
    lastPts = pts;
    pts = 0;
    scans++;
    memset(bins, 0, sizeof(bins));
  }
  if (dist > 0) {
    int b = (int)angle % 360;
    if (bins[b] == 0 || dist < bins[b]) bins[b] = dist;
    pts++;
  }
}

void printDist(const char *label, int deg) {
  if (lastBins[deg] > 0) Serial.printf("%s %5.0f mm  ", label, lastBins[deg]);
  else Serial.printf("%s    -- mm  ", label);
}

void loop() {
  static uint8_t node[5];
  static int idx = 0;

  while (lidar.available()) {
    node[idx++] = lidar.read();
    // resync: start bit and its inverse must differ, check bit must be 1
    if (idx == 1 && ((node[0] & 1) == ((node[0] >> 1) & 1))) idx = 0;
    else if (idx == 2 && !(node[1] & 1)) idx = 0;
    else if (idx == 5) { processNode(node); idx = 0; }
  }

  static unsigned long lastPrint = 0;
  if (millis() - lastPrint >= 1000) {
    lastPrint = millis();
    int nearDeg = -1;
    for (int i = 0; i < 360; i++)
      if (lastBins[i] > 0 && (nearDeg < 0 || lastBins[i] < lastBins[nearDeg])) nearDeg = i;

    Serial.printf("%2d Hz  %4d pts  ", scans, lastPts);
    printDist("0:", 0); printDist("90:", 90); printDist("180:", 180); printDist("270:", 270);
    if (nearDeg >= 0) Serial.printf("nearest %4.0f mm @ %d", lastBins[nearDeg], nearDeg);
    Serial.println();
    scans = 0;
  }
}
