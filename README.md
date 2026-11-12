# CYD Spectrum Analyzer - 频谱与电机转速显示

本项目面向 ES3C28P  ES32-S3 触摸屏开发板：使用板载 ES8311 麦克风采集声音，实时显示频谱、滚动热力图和基于阶次估算的电机转速。

https://www.lcdwiki.com/2.8inch_ESP32-S3_Display


## 硬件

| 部件 | 当前配置 |
| --- | --- |
| 开发板 | ES3C28P，ESP32-S3，16 MB Flash、8 MB OPI PSRAM |
| 显示屏 | 2.8 英寸 ILI9341V，横屏 320 × 240 |
| 触摸屏 | FT6336G 电容触摸，I2C 地址 `0x38` |
| 音频输入 | ES8311 codec 与板载麦克风，单声道 |
| USB | ESP32-S3 原生 USB：烧录，以及按需通过 CDC 虚拟串口输出原始 PCM（见「USB 串口协议」） |

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

## USB 串口协议

设备以 CDC 虚拟串口枚举，Windows、Linux 免驱，Android 可用 usb-serial-for-android 按同一协议解析。串口波特率参数对原生 USB 无效。

### 主机 → 设备（单字节命令）

| 字节 | 含义 |
| --- | --- |
| `S` | 开始二进制流 |
| `P` | 停止二进制流 |
| `I` | 返回一行 `# info ...`（仅在停止状态下回复，避免与二进制帧混杂） |

流开始后固件不再输出 `#` 文本日志；停止后恢复。屏幕显示与采集不受串口是否连接影响。

### 设备 → 主机（帧格式，version 3）

每帧由 32 字节小端头和紧随其后的打包 24 位有符号 PCM 组成。一帧对应一块 2048 个采样（约 46 ms）。

| 偏移 | 类型 | 字段 | 示例值 |
| --- | --- | --- | --- |
| 0 | u32 | magic | `0xAA55AD98`（线上字节 `98 AD 55 AA`） |
| 4 | u16 | version | 3 |
| 6 | u32 | seq | 帧序号，每采集一块加 1 |
| 10 | u32 | sampling_rate | 44100 |
| 14 | u32 | n_samples | 2048（每声道） |
| 18 | u16 | n_channels | 1 |
| 20 | u32 | time_stamp_us | `esp_timer` 时间戳 |
| 24 | f32 | full_scale | 8388608（2^23） |
| 28 | u32 | payload_bytes | `n_samples × n_channels × 3` |
| 32 | — | payload | 24 位小端有符号 PCM，每样本 3 字节 |

接收要点：

- 以 magic 同步；头部字段不合法时跳过 1 字节重新同步。
- **丢帧**：`seq` 不连续即表示设备端丢弃了块（发送槽满）或主机读取过慢。
- 设备端 USB 发送有 200 ms 超时，超时的帧可能被截断，主机靠 magic 重新同步。
- 样本值 = 24 位有符号整数；物理量换算用 `value / full_scale`。

Python 参考实现：[python/pcm_receiver.py](python/pcm_receiver.py)

```bash
pip install pyserial
python python/pcm_receiver.py --port COM5 --info            # 查看设备信息
python python/pcm_receiver.py --port COM5 --out a.wav --seconds 10
```

## 源码导航

| 文件 | 职责 |
| --- | --- |
| [src/main.cpp](src/main.cpp) | ES8311 初始化、I2S 采集、任务调度与 USB 串口流（`S`/`P` 命令控制） |
| [src/spectrum.cpp](src/spectrum.cpp) | FFT、A 计权与总声级计算 |
| [src/display.cpp](src/display.cpp) | 布局、填充、热力图、标记与触摸交互 |
| [src/peak_tracker.h](src/peak_tracker.h) | 门限、确认、平滑与失锁处理 |
| [test/peak_tracker_test.cpp](test/peak_tracker_test.cpp) | 防抖测试入口 `runPeakTests()` |
| [python/pcm_receiver.py](python/pcm_receiver.py) | USB 串口原始 PCM 接收，保存 24 位 WAV，统计丢帧 |

防抖测试覆盖噪声拒绝、连续确认、单帧杂峰、保持门限、超时清空、新峰重锁与计时器回绕；测试入口尚未接入 PlatformIO 自动测试流程。
