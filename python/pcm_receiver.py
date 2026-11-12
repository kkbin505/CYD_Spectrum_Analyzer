#!/usr/bin/env python3
"""Receive raw 24-bit PCM from the CYD spectrum analyser over USB CDC.

Protocol (frame version 3, documented in README.md "USB 串口协议"):
  host -> device   'S' start stream, 'P' stop stream, 'I' print info line
  device -> host   32-byte little-endian header + packed signed 24-bit LE samples

Only the standard library and pyserial are used:
  pip install pyserial

Examples:
  python pcm_receiver.py --port COM5 --info
  python pcm_receiver.py --port COM5 --out capture.wav --seconds 10
  python pcm_receiver.py --port COM5                      # stats only
"""

import argparse
import struct
import sys
import time
import wave
from collections import namedtuple

import serial

MAGIC = 0xAA55AD98
MAGIC_BYTES = struct.pack('<I', MAGIC)  # 98 AD 55 AA on the wire
VERSION = 3
# magic, version, seq, sampling_rate, n_samples, n_channels, time_stamp_us,
# full_scale, payload_bytes
HEADER = struct.Struct('<IHIIIHIfI')
HEADER_SIZE = HEADER.size  # 32
MAX_SAMPLES = 8192         # sanity limit; firmware sends 2048
BAUD = 2000000             # ignored by native USB CDC, kept for clarity
IDLE_TIMEOUT_S = 3.0       # no bytes for this long -> reconnect
REPORT_INTERVAL_S = 5.0

Frame = namedtuple('Frame', 'seq fs n_samples channels ts_us full_scale payload')


class FrameReader:
    """Splits the byte stream into frames, resynchronising on the magic word."""

    def __init__(self, ser):
        self.ser = ser
        self.buf = bytearray()
        self.resyncs = 0

    def frames(self):
        """Yield Frame objects, or None when the port was idle for one read timeout."""
        while True:
            data = self.ser.read(self.ser.in_waiting or 1)
            if not data:
                yield None
                continue
            self.buf += data
            while True:
                frame = self._try_parse()
                if frame is None:
                    break
                yield frame

    def _try_parse(self):
        buf = self.buf
        while True:
            idx = buf.find(MAGIC_BYTES)
            if idx < 0:
                # Keep the last 3 bytes: the magic may be split across reads.
                if len(buf) > 3:
                    self.resyncs += 1
                    del buf[:-3]
                return None
            if idx > 0:
                self.resyncs += 1
                del buf[:idx]
            if len(buf) < HEADER_SIZE:
                return None

            magic, version, seq, fs, n, ch, ts, fullscale, pbytes = \
                HEADER.unpack_from(buf, 0)
            if (magic != MAGIC or version != VERSION or ch == 0
                    or n == 0 or n > MAX_SAMPLES or pbytes != n * ch * 3):
                # False magic hit or corrupted header: skip one byte and retry.
                del buf[:1]
                self.resyncs += 1
                continue

            total = HEADER_SIZE + pbytes
            if len(buf) < total:
                return None
            payload = bytes(buf[HEADER_SIZE:total])
            del buf[:total]
            return Frame(seq, fs, n, ch, ts, fullscale, payload)


class Session:
    """State that must survive a reconnect: the WAV file and running totals."""

    def __init__(self, out_path):
        self.out_path = out_path
        self.wav = None
        self.frames = 0
        self.bytes = 0
        self.dropped = 0

    def write(self, frame):
        if self.out_path and self.wav is None:
            self.wav = wave.open(self.out_path, 'wb')
            self.wav.setnchannels(frame.channels)
            self.wav.setsampwidth(3)  # signed 24-bit LE, same as the wire format
            self.wav.setframerate(frame.fs)
        if self.wav is not None:
            self.wav.writeframes(frame.payload)

    def close(self):
        if self.wav is not None:
            self.wav.close()
            self.wav = None


def query_info(ser, wait_s=0.5):
    """Stop any running stream and print the device's info line."""
    ser.reset_input_buffer()
    ser.write(b'PI')
    ser.flush()
    end = time.time() + wait_s
    while time.time() < end:
        line = ser.readline()
        if line:
            text = line.decode('ascii', errors='replace').strip()
            if text.startswith('#'):
                print(text)


def run_stream(port, session, deadline):
    """Stream until the deadline passes. Raises on serial failure or idle timeout."""
    with serial.Serial(port, BAUD, timeout=0.2) as ser:
        ser.reset_input_buffer()
        ser.write(b'S')
        ser.flush()
        print(f'streaming from {port}')

        reader = FrameReader(ser)
        expected_seq = None
        last_report = time.time()
        rep_bytes = rep_frames = rep_dropped = 0
        idle_since = None

        for frame in reader.frames():
            now = time.time()
            if frame is None:
                if idle_since is None:
                    idle_since = now
                elif now - idle_since > IDLE_TIMEOUT_S:
                    raise IOError('no data from device')
                if deadline and now >= deadline:
                    return
                continue
            idle_since = None

            # A sequence gap means blocks were dropped on the device (no free
            # TX slot) or the host fell behind.
            if expected_seq is not None:
                gap = (frame.seq - expected_seq) & 0xFFFFFFFF
                if gap:
                    rep_dropped += gap
                    session.dropped += gap
            expected_seq = (frame.seq + 1) & 0xFFFFFFFF

            session.write(frame)
            session.frames += 1
            session.bytes += len(frame.payload)
            rep_frames += 1
            rep_bytes += len(frame.payload)

            if now - last_report >= REPORT_INTERVAL_S:
                span = now - last_report
                print(f'frames={rep_frames / span:5.1f}/s '
                      f'rate={rep_bytes / span / 1024:6.1f} KB/s '
                      f'dropped={rep_dropped} resyncs={reader.resyncs}')
                last_report = now
                rep_bytes = rep_frames = rep_dropped = 0

            if deadline and now >= deadline:
                return


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--port', required=True, help='e.g. COM5 (Windows) or /dev/ttyACM0')
    ap.add_argument('--out', help='write samples to this WAV file (24-bit)')
    ap.add_argument('--seconds', type=float, default=0,
                    help='stop after this many seconds (0 = until Ctrl+C)')
    ap.add_argument('--info', action='store_true', help='print device info and exit')
    args = ap.parse_args()

    if args.info:
        with serial.Serial(args.port, BAUD, timeout=0.2) as ser:
            query_info(ser)
        return 0

    deadline = time.time() + args.seconds if args.seconds > 0 else None
    session = Session(args.out)
    started = time.time()
    try:
        while True:
            try:
                run_stream(args.port, session, deadline)
            except (serial.SerialException, IOError, OSError) as exc:
                # Native USB re-enumerates the COM port on reset; keep retrying.
                print(f'# link lost ({exc}); retrying in 1 s')
                time.sleep(1.0)
            if deadline and time.time() >= deadline:
                break
    except KeyboardInterrupt:
        pass
    finally:
        # Best-effort: tell the device to stop streaming.
        try:
            with serial.Serial(args.port, BAUD, timeout=0.2) as ser:
                ser.write(b'P')
                ser.flush()
        except (serial.SerialException, OSError):
            pass
        session.close()

    elapsed = max(time.time() - started, 1e-6)
    print(f'done: frames={session.frames} dropped={session.dropped} '
          f'avg={session.bytes / elapsed / 1024:.1f} KB/s '
          f'out={args.out or "(none)"}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
