#pragma once

#include <stdint.h>

// 2.8" 240x320 ILI9341V display on the ES3C28P board, used in landscape.
namespace display {

// true: scrolling dBA heat map (frequency across, time down, one row per 0.5 s).
// false: narrowband line spectrum.
constexpr bool kHeatmapMode = true;

void begin();

// dba_bins: one-sided A-weighted spectrum (spectrum::dbaBins()).
void update(const float *dba_bins, uint16_t bin_count, float bin_hz,
            float dba, float spl, float peak);

}  // namespace display
