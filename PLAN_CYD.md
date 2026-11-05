# CYD 分支计划：ES3C28P 麦克风采集验证

分支：`CYD`（从 `INMP441` 切出，当前有未提交改动）
目标板：ES3C28P / ES3N28P 2.8" ESP32-S3 显示模块（带 ES8311 codec + MEMS 麦克风）

## 第一步：烧录并用 Python 读取数据（当前进行中）

1. **修复 PlatformIO 编译环境**
   - 现象：`pio run -e esp32-s3-devkitc-1` 报 `Failed to install Python dependencies into penv`，退出码 2。
   - 已尝试：
     - 用 `pip install` 装了 ESP-IDF 的依赖（urllib3、cryptography、future、pyparsing、kconfiglib、idf-component-manager、esp-idf-kconfig）。
     - 其中 `cryptography` 曾被装成 3.4.8，后又恢复为 50.0.2；`pyparsing` 为 3.0.9，`urllib3` 为 1.26.20。
   - 下一步：找到真正报错的安装命令（错误信息来自 PlatformIO 的 Python 依赖安装流程，需要定位），按报错修正依赖版本。
   - 注意：这些是全局 PlatformIO penv 的改动，会影响其他项目。
2. **编译**：`pio run -e esp32-s3-devkitc-1`，确认 `mck_io_num`、`fixed_mclk` 等 I2S 字段编译通过。
3. **烧录**：`pio run -e esp32-s3-devkitc-1 -t upload`。
   - 串口：COM11（USB 设备，VID 0x303A / PID 0x1001，ESP32-S3 原生 USB CDC）。
   - 如果无法自动进入下载模式：按住 BOOT，再按一下 RST。
4. **串口检查**：用 115200 或任意波特率打开 COM11，应看到：
   - `# ES8311 configured`
   - 若出现 `# fatal: ES8311 I2C configuration failed`，说明 I2C（GPIO16/15，地址 0x18）写入失败，先查接线和地址。
5. **Python 读取脚本**（新建，放在 `python/` 下，例如 `python/cyd_read.py`）：
   - 打开串口（2 Mbps）。
   - 在字节流中搜索帧头 magic `0xAA55AD98`（小端序 bytes：`98 AD 55 AA`）。
   - 解析 32 字节帧头：version、seq、sampling_rate、n_samples、n_channels、time_stamp_us、full_scale、payload_bytes。
   - 读取 payload（24 bit 小端，有符号），转成 float（除以 2^23）。
   - 检查：
     - 采样率是否为 44100；
     - seq 是否连续（统计丢帧）；
     - 样本是否全为 0（若全为 0，说明 codec 没有输出，需检查 MCLK/BCLK/LRCK 和寄存器）；
     - 输出 RMS 和 dBFS，保存一段原始数据到 `.npy` 或 `.wav` 便于事后检查。
6. **验收标准**：
   - 能稳定解析帧，seq 基本连续；
   - 安静环境与拍手/说话时，RMS 有明显变化；
   - 不是全零，也不是固定的直流值。

## 第二步：屏幕显示实时频谱与 SPL / dBA

- 采样率：44.1 kHz。
- 频带：20 Hz – 20 kHz。
- FFT 参数（参考用户给的截图）：
  - Spectrum Size：4096
  - 窗函数：Hanning
  - Overlap：50%
  - Amplitude Scaling：RMS
  - 频率分辨率约 10.8 Hz（44100 / 4096）
- 屏幕显示：
  - 实时频谱曲线（20 Hz – 20 kHz，对数频率轴）；
  - 当前 SPL（dB，未加权）；
  - 频带内的 dBA（A 计权后的总声级）。
- 注意：
  - 数字麦克风没有出厂校准，SPL 为相对值，需要用已知声源（如 94 dB 校准器）标定增益常数；
  - ESP32-S3 做 4096 点 FFT 需要确认算力和内存是否够（可用 arduinoFFT，已在 `platformio.ini` 的 lib_deps 中）。
- 验收标准：屏幕刷新频谱，SPL 和 dBA 数值随声音变化合理。

## 第三步：Wi-Fi 无线传输（待定）

- 验证 ESP32-S3 通过 Wi-Fi（2.4 GHz）把帧流发给 PC 或手机（UDP 或 TCP）。
- 复用第一步的帧格式，加上序号检查。
- 记录丢包率、延迟和实际距离。
- 注意：8812CU 方案暂不纳入这一步。

## 待办 / 已知风险

- ES8311 的 44.1 kHz 时钟分频值来自 ESPHome 驱动的推算，需要在硬件上验证。
- 麦克风增益寄存器（0x14 / 0x16 / 0x17）的值未按测量需求调整。
- MCLK 在 GPIO4 上是否可输出，需要实测确认。
- 第一步完成后再提交 `CYD` 分支的改动，提交前需要用户确认。
