#include <Wire.h>

// OV7670 SCCB address (7-bit)
#define CAM_ADDR 0x21

// Control pins
#define PIN_VSYNC 2    // PD2
#define PIN_HREF  A0   // PC0
#define PIN_PCLK  A1   // PC1
// XCLK on D3 (Timer2 hardware)
// RESET  → wire directly to 3.3V
// PWDN   → wire directly to GND

// Data pins:  camera D0-D2 = Arduino D5-D7 (PD5-7)
//             camera D3-D7 = Arduino D8-D12 (PB0-4)
inline uint8_t readPixelByte() {
  return ((PIND >> 5) & 0x07) | ((PINB & 0x1F) << 3);
}

bool camWrite(uint8_t reg, uint8_t val) {
  Wire.beginTransmission(CAM_ADDR);
  Wire.write(reg);
  Wire.write(val);
  return Wire.endTransmission() == 0;
}

void camInit() {
  camWrite(0x12, 0x80);  // software reset
  delay(200);

  // RGB565 output
  camWrite(0x12, 0x04);  // COM7: RGB mode
  camWrite(0x40, 0xD0);  // COM15: RGB565 full range
  camWrite(0x8C, 0x00);  // RGB444: off
  camWrite(0x3A, 0x04);  // TSLB
  camWrite(0x3D, 0xC0);  // COM13

  // Slow down PCLK so UNO can read it
  camWrite(0x11, 0x01);  // CLKRC: prescaler /2 → internal 4MHz
  camWrite(0x3E, 0x1A);  // COM14: PCLK divider on, /4
  camWrite(0x73, 0xF1);  // SCALING_PCLK_DIV: /2
  // Effective PCLK ≈ 500 KHz → Arduino has ~32 cycles per clock edge

  // QCIF output (176×144)
  camWrite(0x0C, 0x04);  // COM3: scale enable
  camWrite(0x3E, 0x1A);  // COM14
  camWrite(0x70, 0x3A);  // SCALING_XSC
  camWrite(0x71, 0x35);  // SCALING_YSC
  camWrite(0x72, 0x11);  // SCALING_DCWCTR: /2 H and V
  camWrite(0xA2, 0x02);  // SCALING_PCLK_DELAY

  // Window for QCIF
  camWrite(0x17, 0x13);  // HSTART
  camWrite(0x18, 0x01);  // HSTOP
  camWrite(0x32, 0xB6);  // HREF reg
  camWrite(0x19, 0x02);  // VSTART
  camWrite(0x1A, 0x7A);  // VSTOP
  camWrite(0x03, 0x0A);  // VREF

  // Auto white balance + auto exposure
  camWrite(0x13, 0xE7);  // COM8: AWB, AEC, AGC all on
  camWrite(0x6B, 0x0A);  // DBLV: bypass PLL
}

const char* detectColor(uint8_t r, uint8_t g, uint8_t b) {
  uint8_t hi = max(r, max(g, b));
  uint8_t lo = min(r, min(g, b));

  if ((hi - lo) < 40) {
    if (hi > 180) return "WHITE";
    if (hi < 60)  return "BLACK";
    return "GREY";
  }

  if (r >= g && r >= b) {
    if (g > b + 30) return "YELLOW";
    return "RED";
  }
  if (g >= r && g >= b) {
    if (r > b + 20) return "YELLOW";
    return "GREEN";
  }
  if (r > 120) return "PURPLE";
  return "BLUE";
}

// Capture one frame, average the 20x20 center patch (QCIF 176x144)
void sampleFrame(uint8_t &outR, uint8_t &outG, uint8_t &outB) {
  long sumR = 0, sumG = 0, sumB = 0;
  int  count = 0;

  // Wait for VSYNC falling = start of frame
  while (!(PIND & 0x04));
  while  (PIND & 0x04);

  for (int row = 0; row < 144; row++) {
    while (!(PINC & 0x01));  // wait HREF high

    if (row >= 62 && row <= 81) {
      // Sample this row pixel by pixel
      for (int col = 0; col < 176; col++) {
        while (!(PINC & 0x02)); uint8_t hi = readPixelByte(); while (PINC & 0x02);
        while (!(PINC & 0x02)); uint8_t lo = readPixelByte(); while (PINC & 0x02);

        if (col >= 78 && col <= 97) {
          uint16_t px = ((uint16_t)hi << 8) | lo;
          sumR += ((px >> 11) & 0x1F);  // 5-bit red
          sumG += ((px >> 5)  & 0x3F);  // 6-bit green
          sumB += ( px        & 0x1F);  // 5-bit blue
          count++;
        }
      }
    } else {
      // Non-sampled row: just wait for HREF to fall
    }

    while (PINC & 0x01);  // wait HREF low
  }

  if (count > 0) {
    outR = (sumR / count) * 255 / 31;
    outG = (sumG / count) * 255 / 63;
    outB = (sumB / count) * 255 / 31;
  }
}

bool cameraOk = false;

void setup() {
  Serial.begin(115200);

  // Data pins: inputs
  DDRD &= ~0b11100000;  // D5,D6,D7
  DDRB &= ~0b00011111;  // D8-D12

  // Control pins: inputs
  pinMode(PIN_VSYNC, INPUT);
  pinMode(PIN_HREF,  INPUT);
  pinMode(PIN_PCLK,  INPUT);

  // XCLK on D3 via Timer2 toggle = 8MHz
  pinMode(3, OUTPUT);
  TCCR2A = _BV(COM2B0) | _BV(WGM21);
  TCCR2B = _BV(CS20);
  OCR2A  = 0;

  Wire.begin();
  Wire.setClock(100000);
  delay(500);

  Serial.print("Looking for OV7670... ");
  Wire.beginTransmission(CAM_ADDR);
  cameraOk = (Wire.endTransmission() == 0);

  if (cameraOk) {
    Serial.println("Found!");
    camInit();
    delay(1000);  // let AWB settle
    Serial.println("Point camera at object. Reading color every second.");
  } else {
    Serial.println("NOT FOUND");
    Serial.println("Check: 3.3V, GND, A4=SIOD, A5=SIOC, D3=XCLK");
  }
}

void loop() {
  if (!cameraOk) {
    delay(2000);
    Wire.beginTransmission(CAM_ADDR);
    cameraOk = (Wire.endTransmission() == 0);
    if (cameraOk) { camInit(); delay(1000); }
    return;
  }

  uint8_t r = 0, g = 0, b = 0;
  sampleFrame(r, g, b);

  Serial.print("R="); Serial.print(r);
  Serial.print("  G="); Serial.print(g);
  Serial.print("  B="); Serial.print(b);
  Serial.print("  ->  ");
  Serial.println(detectColor(r, g, b));

  delay(200);
}
