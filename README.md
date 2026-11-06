# CYD Spectrum Analyzer - 频谱与电机转速显示

本项目面向 ES3C28P  ES32-S3 触摸屏开发板：使用板载 ES8311 麦克风采集声音，实时显示频谱、滚动热力图和基于阶次估算的电机转速。

<img width="320" height="240" alt="cyd_screen_02" src="https://github.com/user-attachments/assets/280a5927-62f8-4ac1-af7a-a08ea7d8c3ad" />


https://www.lcdwiki.com/2.8inch_ESP32-S3_Display


## 硬件

| 部件 | 当前配置 |
| --- | --- |
| 开发板 | ES3C28P，ESP32-S3，16 MB Flash、8 MB OPI PSRAM |
| 显示屏 | 2.8 英寸 ILI9341V，横屏 320 × 240 |
| 触摸屏 | FT6336G 电容触摸，I2C 地址 `0x38` |
| 音频输入 | ES8311 codec 与板载麦克风，单声道 |
| USB | ESP32-S3 原生 USB，用于烧录及可选采集 |

ES3N28P 没有电容触摸，不能通过屏幕调整阶次。

| 板载连接 | GPIO |
| --- | --- |
| LCD SCK / MOSI / MISO | 12 / 11 / 13 |
| LCD CS / D-C / 背光 | 10 / 46 / 45 |
| 共用 I2C SDA / SCL | 16 / 15 |
| 触摸复位 | 18 |
| ES8311 MCLK / BCLK / LRCK / 数据输入 | 4 / 5 / 7 / 6 |
| 功放使能 | 1，当前保持关闭 |

## 屏幕与操作

- **左侧**：70 像素数值与设置栏，显示总 dBA、未加权 SPL 和启动以来最高 SPL（`pk`）。
- **阶次设置**：竖排 `Order → ▲ → 数字 → ▼`；上箭头加 1，下箭头减 1。默认 10 阶，范围 1～65535；按住不连发，重启恢复 10 阶。
- **右上**：实时频谱，约占绘图区高度四分之一；纵轴为 20～80 dBA，曲线下方深蓝渐变填充。
- **右下**：滚动热力图，每 0.5 秒增加一行，最新数据在顶部；颜色范围为 30～60 dBA，超过上限使用最亮颜色。
- **横坐标**：两图共用 20 Hz～20 kHz 对数频率轴与像素映射，频率位置上下对齐。
- **峰值标记**：红色竖线跟随确认后的峰；白色标签固定在距屏幕顶部 5 像素处，格式为 `62dBA @ 269Hz 1614RPM`。


顶部 dBA 为跟踪峰的频点幅值，左栏大号 dBA 为总 A 计权声级。读数尚未完成声学校准，用于相对比较，不应视为已校准声级计的测量结果。

## 电机转速估算

```text
RPM = 峰值频率（Hz）× 60 ÷ 阶次
```

例如，500 Hz 的峰对应第 10 阶时，转速为 3000 RPM。修改阶次后，顶部 RPM 立即重新计算。

阶次需与电机声学特征或谐波对应；软件不会自动辨识阶次。其他更响的声音也可能成为候选峰。FFT 间隔约为 10.77 Hz，在 10 阶下约为 64.6 RPM/频点；显示平滑不提高实际频率分辨率。

## 信号分析参数

| 参数 | 当前值 |
| --- | --- |
| 采样率 | 44.1 kHz |
| 输入 | 24 位 PCM，以 32 位 I2S 槽接收 |
| FFT | 4096 点，Hann 窗，50% 重叠 |
| 频率间隔 | 44100 / 4096 ≈ 10.77 Hz |
| 幅值 | 单边谱、RMS 缩放、A 计权 |
| 声级偏移 | `kSplOffsetDb = 140`，需按实际麦克风与校准结果调整 |

采集、分析与显示分任务运行，单块队列优先保留最新音频块；显示跟不上时会跳过部分分析块。

## 源码导航

| 文件 | 职责 |
| --- | --- |
| [src/main.cpp](src/main.cpp) | ES8311 初始化、I2S 采集、任务调度与可选 USB 流 |
| [src/spectrum.cpp](src/spectrum.cpp) | FFT、A 计权与总声级计算 |
| [src/display.cpp](src/display.cpp) | 布局、填充、热力图、标记与触摸交互 |
| [src/peak_tracker.h](src/peak_tracker.h) | 门限、确认、平滑与失锁处理 |
| [test/peak_tracker_test.cpp](test/peak_tracker_test.cpp) | 防抖测试入口 `runPeakTests()` |
| [python/ad9833_stream.py](python/ad9833_stream.py) | USB 接收、仿真与 TDMS 保存 |
| [python/usb2406_stream.py](python/usb2406_stream.py) | USB2406 采集与 TDMS 保存 |

防抖测试覆盖噪声拒绝、连续确认、单帧杂峰、保持门限、超时清空、新峰重锁与计时器回绕；测试入口尚未接入 PlatformIO 自动测试流程。
