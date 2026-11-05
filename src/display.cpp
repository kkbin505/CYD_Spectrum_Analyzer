#include "display.h"

#include <math.h>
#include <stdio.h>
#include <string.h>

#define LGFX_USE_V1
#include <LovyanGFX.hpp>

namespace display {
namespace {

// --- Board wiring (ES3C28P / ES3N28P, see the module pinout) --------------
constexpr int kPinSck = 12;
constexpr int kPinMosi = 11;
constexpr int kPinMiso = 13;
constexpr int kPinCs = 10;
constexpr int kPinDc = 46;
constexpr int kPinBl = 45;
constexpr uint32_t kSpiHz = 40000000;

class LGFX : public lgfx::LGFX_Device {
  lgfx::Panel_ILI9341 panel_;
  lgfx::Bus_SPI bus_;
  lgfx::Light_PWM light_;

 public:
  LGFX() {
    {
      auto cfg = bus_.config();
      cfg.spi_host = SPI2_HOST;
      cfg.spi_mode = 0;
      cfg.freq_write = kSpiHz;
      cfg.pin_sclk = kPinSck;
      cfg.pin_mosi = kPinMosi;
      cfg.pin_miso = kPinMiso;
      cfg.pin_dc = kPinDc;
      bus_.config(cfg);
      panel_.setBus(&bus_);
    }
    {
      auto cfg = panel_.config();
      cfg.pin_cs = kPinCs;
      cfg.pin_rst = -1;  // shares the ESP32 reset line
      cfg.panel_width = 240;
      cfg.panel_height = 320;
      cfg.bus_shared = true;
      cfg.invert = true;  // IPS panel needs colour inversion
      panel_.config(cfg);
    }
    {
      auto cfg = light_.config();
      cfg.pin_bl = kPinBl;
      light_.config(cfg);
      panel_.setLight(&light_);
    }
    setPanel(&panel_);
  }
};

LGFX tft;
LGFX_Sprite plot(&tft);

// Landscape: 320 x 240 after setRotation(1).
constexpr int kScreenW = 320;
constexpr int kScreenH = 240;

constexpr int kTopH = 32;
constexpr int kPlotX = 40;
constexpr int kPlotY = kTopH;
constexpr int kPlotW = kScreenW - kPlotX - 4;  // 276
constexpr int kPlotH = 186;  // fills down to the frequency labels at the bottom
constexpr int kLabelY = kPlotY + kPlotH + 4;   // 200

// Logarithmic frequency axis, 20 Hz .. 20 kHz.
constexpr float kFreqMin = 20.0f;
constexpr float kFreqMax = 20000.0f;

// Line mode: dBA scale of the plot. Levels are relative until the microphone
// is calibrated, so treat these as display limits rather than absolute SPL.
constexpr float kDbMin = 20.0f;
constexpr float kDbMax = 110.0f;

// Heat map mode: black at or below kHeatFloorDb, brightest colour at kHeatTopDb.
// Change kHeatTopDb to rescale the colour range.
constexpr float kHeatFloorDb = 30.0f;
constexpr float kHeatTopDb = 60.0f;
constexpr uint32_t kHeatRowMs = 500;  // one spectrum row every 0.5 s

const uint16_t kBg = lgfx::color565(6, 8, 12);
const uint16_t kBlack = lgfx::color565(0, 0, 0);
const uint16_t kGrid = lgfx::color565(38, 44, 54);
const uint16_t kLine = lgfx::color565(90, 200, 245);
const uint16_t kGrey = lgfx::color565(140, 150, 160);
const uint16_t kWhite = lgfx::color565(235, 240, 245);
const uint16_t kGreen = lgfx::color565(80, 220, 120);

uint16_t gLoBin[kPlotW];
uint16_t gHiBin[kPlotW];
bool gMapped = false;

// Heat map: per-column maximum over all spectra in the current 0.5 s window.
float gRowMax[kPlotW];

int yOf(float db) {
  float t = (kDbMax - db) / (kDbMax - kDbMin);
  if (t < 0.0f) t = 0.0f;
  if (t > 1.0f) t = 1.0f;
  return static_cast<int>(t * (kPlotH - 1));
}

int xOf(float freq) {
  if (freq <= kFreqMin) return kPlotX;
  const float t = log10f(freq / kFreqMin) / log10f(kFreqMax / kFreqMin);
  return kPlotX + static_cast<int>(lroundf(t * (kPlotW - 1)));
}

// inferno-style palette: black -> purple -> magenta -> orange -> pale yellow.
uint16_t heatColor(float db) {
  float t = (db - kHeatFloorDb) / (kHeatTopDb - kHeatFloorDb);
  if (t <= 0.0f) return kBlack;
  if (t > 1.0f) t = 1.0f;

  static const uint8_t kStops[5][3] = {
      {0, 0, 4}, {87, 16, 110}, {188, 55, 84}, {249, 142, 9}, {252, 255, 164}};
  const float pos = t * 4.0f;
  int i = static_cast<int>(pos);
  if (i >= 4) i = 3;
  const float f = pos - i;
  uint8_t rgb[3];
  for (int c = 0; c < 3; ++c) {
    const float a = kStops[i][c];
    const float b = kStops[i + 1][c];
    rgb[c] = static_cast<uint8_t>(lroundf(a + (b - a) * f));
  }
  return lgfx::color565(rgb[0], rgb[1], rgb[2]);
}

// Frequency labels under the plot; shared by both modes.
void drawFreqLabels() {
  tft.setFont(&lgfx::fonts::Font0);  // small: 10k and 20k sit close together
  tft.setTextColor(kGrey, kBg);
  const float ticks[] = {20.0f, 100.0f, 1000.0f, 10000.0f, 20000.0f};
  const char *labels[] = {"20", "100", "1k", "10k", "20k"};
  for (int i = 0; i < 5; ++i) {
    const int x = xOf(ticks[i]);
    if (i == 0) {
      tft.drawString(labels[i], x, kLabelY);
    } else if (i == 4) {
      tft.drawRightString(labels[i], x, kLabelY);
    } else {
      tft.drawCenterString(labels[i], x, kLabelY);
    }
  }
}

void drawLineAxisLabels() {
  tft.setFont(&lgfx::fonts::Font2);
  tft.setTextColor(kGrey, kBg);
  for (int db = 30; db <= 110; db += 20) {
    const int y = kPlotY + yOf(static_cast<float>(db));
    tft.drawRightString(String(db), kPlotX - 4, y - 8);
  }
  drawFreqLabels();
}

void drawHeatAxisLabels() {
  // Rows are 0.5 s apart, so 2 rows per second; the top row is "now".
  tft.setFont(&lgfx::fonts::Font2);
  tft.setTextColor(kGrey, kBg);
  const int rows_per_s = 1000 / kHeatRowMs;
  for (int s = 0; s <= 80; s += 20) {
    const int y = kPlotY + s * rows_per_s;
    char buf[12];
    snprintf(buf, sizeof(buf), s == 0 ? "0s" : "-%ds", s);
    tft.drawRightString(buf, kPlotX - 4, s == 0 ? y : y - 8);
  }
  drawFreqLabels();
}

void drawTopBar(float dba, float spl, float peak) {
  char buf[24];

  tft.fillRect(0, 0, kScreenW, kTopH, kBg);

  tft.setFont(&lgfx::fonts::Font2);
  tft.setTextColor(kGrey, kBg);
  tft.drawString("[dBA]", 4, 8);

  tft.setFont(&lgfx::fonts::Font4);
  tft.setTextColor(kWhite, kBg);
  snprintf(buf, sizeof(buf), "%.1f", dba);
  tft.drawString(buf, 50, 2);

  tft.setFont(&lgfx::fonts::Font2);
  tft.setTextColor(kGrey, kBg);
  snprintf(buf, sizeof(buf), "SPL %.1f", spl);
  tft.drawRightString(buf, kScreenW - 78, 8);
  tft.setTextColor(kGreen, kBg);
  snprintf(buf, sizeof(buf), "pk %.1f", peak);
  tft.drawRightString(buf, kScreenW - 4, 8);
}

void buildMapping(float bin_hz, uint16_t bin_count) {
  const int last_bin = static_cast<int>(bin_count) - 1;
  for (int x = 0; x < kPlotW; ++x) {
    // Each column covers a half-column either side of its centre, on the
    // log scale, so the bins inside it are the ones it is drawn from.
    const float ratio = kFreqMax / kFreqMin;
    const float f_lo = kFreqMin * powf(ratio, (x - 0.5f) / (kPlotW - 1));
    const float f_hi = kFreqMin * powf(ratio, (x + 0.5f) / (kPlotW - 1));
    int lo = static_cast<int>(ceilf(f_lo / bin_hz));
    int hi = static_cast<int>(floorf(f_hi / bin_hz));
    if (lo < 1) lo = 1;  // skip DC
    if (hi > last_bin) hi = last_bin;
    if (hi < lo) hi = lo;
    gLoBin[x] = static_cast<uint16_t>(lo);
    gHiBin[x] = static_cast<uint16_t>(hi);
  }
  gMapped = true;
}

// Largest dBA bin inside screen column x.
float columnLevel(const float *dba_bins, int x) {
  float best = -200.0f;
  for (int k = gLoBin[x]; k <= gHiBin[x]; ++k) {
    if (dba_bins[k] > best) best = dba_bins[k];
  }
  return best;
}

void drawLineCurve(const float *dba_bins) {
  plot.fillSprite(kBg);

  for (int db = 30; db <= 110; db += 20) {
    plot.drawFastHLine(0, yOf(static_cast<float>(db)), kPlotW, kGrid);
  }
  const float grid_hz[] = {100.0f, 1000.0f, 10000.0f};
  for (float f : grid_hz) {
    const int x = xOf(f) - kPlotX;
    plot.drawFastVLine(x, 0, kPlotH, kGrid);
  }

  int prev_y = -1;
  for (int x = 0; x < kPlotW; ++x) {
    const int y = yOf(columnLevel(dba_bins, x));
    if (prev_y >= 0) {
      plot.drawLine(x - 1, prev_y, x, y, kLine);
    } else {
      plot.drawPixel(x, y, kLine);
    }
    prev_y = y;
  }
}

// Heat map: shift the whole sprite down one row (raw byte move, sprite is
// 16 bpp with no padding), then write the newest spectrum into row 0.
void pushHeatRow(const float *row_db) {
  uint8_t *buf = static_cast<uint8_t *>(plot.getBuffer());
  const size_t row_bytes = kPlotW * sizeof(uint16_t);
  memmove(buf + row_bytes, buf, row_bytes * (kPlotH - 1));

  for (int x = 0; x < kPlotW; ++x) {
    plot.drawPixel(x, 0, heatColor(row_db[x]));
  }
  plot.pushSprite(kPlotX, kPlotY);
}

}  // namespace

void begin() {
  for (int x = 0; x < kPlotW; ++x) gRowMax[x] = -200.0f;
  tft.init();
  tft.setRotation(3);  // landscape, 320 x 240, rotated 180 degrees from rotation 1
  tft.setBrightness(255);
  tft.fillScreen(kBg);

  plot.setColorDepth(16);
  plot.setPsram(true);
  if (plot.createSprite(kPlotW, kPlotH) == nullptr) {
    plot.setPsram(false);
    if (plot.createSprite(kPlotW, kPlotH) == nullptr) {
      tft.setFont(&lgfx::fonts::Font2);
      tft.setTextColor(kWhite, kBg);
      tft.drawString("plot buffer alloc failed", 8, 40);
      return;
    }
  }
  plot.fillSprite(kHeatmapMode ? kBlack : kBg);

  if (kHeatmapMode) {
    drawHeatAxisLabels();
  } else {
    drawLineAxisLabels();
  }
  drawTopBar(0.0f, 0.0f, 0.0f);
}

void update(const float *dba_bins, uint16_t bin_count, float bin_hz,
            float dba, float spl, float peak) {
  if (!gMapped) {
    if (bin_hz <= 0.0f) return;
    buildMapping(bin_hz, bin_count);
  }
  if (plot.getBuffer() == nullptr) return;

  const uint32_t now = millis();

  if (kHeatmapMode) {
    // Fold this spectrum into the current window's per-column maximum.
    for (int x = 0; x < kPlotW; ++x) {
      const float v = columnLevel(dba_bins, x);
      if (v > gRowMax[x]) gRowMax[x] = v;
    }

    static uint32_t last_row = 0;
    if (now - last_row >= kHeatRowMs) {
      pushHeatRow(gRowMax);
      for (int x = 0; x < kPlotW; ++x) gRowMax[x] = -200.0f;
      last_row = now;
    }
  } else {
    drawLineCurve(dba_bins);
    plot.pushSprite(kPlotX, kPlotY);
  }

  static uint32_t last_text = 0;
  if (now - last_text >= 200) {
    drawTopBar(dba, spl, peak);
    last_text = now;
  }
}

}  // namespace display
