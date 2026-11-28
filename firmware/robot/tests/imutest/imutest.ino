#include <Wire.h>
#include <Adafruit_LSM6DSOX.h>

#define IMU_SCL 39
#define IMU_SDA 40

Adafruit_LSM6DSOX imu;

void setup() {
  Serial.begin(115200);
  delay(1000);
  Wire.begin(IMU_SDA, IMU_SCL);

  Serial.println("I2C scan:");
  for (uint8_t addr = 1; addr < 127; addr++) {
    Wire.beginTransmission(addr);
    if (Wire.endTransmission() == 0) Serial.printf("  found 0x%02X\n", addr);
  }

  if (!imu.begin_I2C(0x6A, &Wire)) {
    Serial.println("LSM6DSOX not found at 0x6A");
    while (true) delay(1000);
  }
  imu.setAccelRange(LSM6DS_ACCEL_RANGE_4_G);
  imu.setGyroRange(LSM6DS_GYRO_RANGE_500_DPS);
  imu.setAccelDataRate(LSM6DS_RATE_104_HZ);
  imu.setGyroDataRate(LSM6DS_RATE_104_HZ);
  Serial.println("IMU ready\n");
}

void loop() {
  sensors_event_t a, g, t;
  imu.getEvent(&a, &g, &t);

  float ax = a.acceleration.x, ay = a.acceleration.y, az = a.acceleration.z;
  float mag = sqrt(ax * ax + ay * ay + az * az);
  float pitch = atan2(-ax, sqrt(ay * ay + az * az)) * 180.0 / PI;
  float roll = atan2(ay, az) * 180.0 / PI;

  Serial.printf("acc %6.2f %6.2f %6.2f  |a| %5.2f   gyro %7.1f %7.1f %7.1f dps   pitch %6.1f  roll %6.1f\n",
                ax, ay, az, mag,
                g.gyro.x * 57.3, g.gyro.y * 57.3, g.gyro.z * 57.3,
                pitch, roll);
  delay(100);
}