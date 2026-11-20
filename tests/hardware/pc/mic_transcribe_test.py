#!/usr/bin/env python3
"""Smart Home Hub - mic + mute transcription test (PC side).

The ESP32 streams raw 16 kHz mono PCM16. This script detects speech by energy,
transcribes each utterance with faster-whisper, and sends the text back as lines.
"""
import argparse
import collections
import queue
import socket
import threading
import time

import numpy as np
from faster_whisper import WhisperModel

RATE = 16000
FRAME = 480                 # 30 ms
FRAME_MS = 30
FRAME_BYTES = FRAME * 2


def level_db(frame):
    x = frame.astype(np.float32)
    return 20 * np.log10(np.sqrt(np.mean(x * x)) / 32768.0 + 1e-9)


class Segmenter:
    """Energy VAD with an adaptive noise floor."""

    def __init__(self, args, on_utterance):
        self.a = args
        self.on_utterance = on_utterance
        self.noise = -60.0
        self.preroll = collections.deque(maxlen=max(1, args.preroll_ms // FRAME_MS))
        self.reset()

    def reset(self):
        self.active = False
        self.frames = []
        self.loud = 0
        self.quiet_ms = 0

    def threshold(self):
        return max(self.noise + self.a.margin, self.a.min_db)

    def push(self, frame):
        lvl = level_db(frame)
        th = self.threshold()
        if not self.active:
            self.preroll.append(frame)
            if lvl > th:
                self.loud += 1
                if self.loud >= 3:                       # 90 ms above threshold
                    self.active = True
                    self.frames = list(self.preroll)
                    self.preroll.clear()
            else:
                self.loud = 0
                self.noise += 0.05 * (lvl - self.noise)  # track floor only when quiet
        else:
            self.frames.append(frame)
            self.quiet_ms = self.quiet_ms + FRAME_MS if lvl < th else 0
            too_long = len(self.frames) * FRAME_MS >= self.a.max_s * 1000
            if self.quiet_ms >= self.a.hangover_ms or too_long:
                self.flush()
        return lvl

    def flush(self):
        if self.active and len(self.frames) * FRAME_MS >= self.a.min_ms:
            audio = np.concatenate(self.frames).astype(np.float32) / 32768.0
            self.on_utterance(audio)
        self.reset()


def transcriber(model, jobs):
    while True:
        audio, send_line = jobs.get()
        t0 = time.time()
        segments, _ = model.transcribe(audio, language="en", beam_size=1, vad_filter=True)
        text = " ".join(s.text.strip() for s in segments).strip()
        dur = len(audio) / RATE
        if not text:
            print(f"[stt] {dur:.1f}s of audio, no words")
            continue
        print(f"[stt] {dur:.1f}s audio, {time.time() - t0:.2f}s: {text}")
        try:
            send_line(text)
        except OSError:
            print("[stt] ESP gone, transcript not delivered")


def handle_client(conn, addr, jobs, args):
    print(f"[hub] ESP connected from {addr[0]}")
    send_lock = threading.Lock()

    def send_line(text):
        with send_lock:
            conn.sendall((text + "\n").encode("utf-8"))

    seg = Segmenter(args, lambda audio: jobs.put((audio, send_line)))
    conn.settimeout(0.5)
    buf = bytearray()
    last_meter = 0.0
    try:
        while True:
            try:
                data = conn.recv(4096)
            except socket.timeout:
                seg.flush()              # stream paused (muted) -> close out any utterance
                continue
            if not data:
                break
            buf += data
            while len(buf) >= FRAME_BYTES:
                frame = np.frombuffer(bytes(buf[:FRAME_BYTES]), dtype="<i2")
                del buf[:FRAME_BYTES]
                lvl = seg.push(frame)
                if args.meter and time.time() - last_meter > 0.5:
                    last_meter = time.time()
                    print(f"  level {lvl:6.1f} dBFS | floor {seg.noise:6.1f} | "
                          f"threshold {seg.threshold():6.1f}")
    except OSError:
        pass
    finally:
        seg.flush()
        conn.close()
        print("[hub] ESP disconnected")


def main():
    p = argparse.ArgumentParser(description="Smart Home Hub mic+mute STT test (PC side)")
    p.add_argument("--port", type=int, default=7777)
    p.add_argument("--model", default="base.en", help="tiny.en / base.en / small.en ...")
    p.add_argument("--device", default="cpu", help="cpu or cuda")
    p.add_argument("--compute", default="int8", help="int8 on CPU, float16 on CUDA")
    p.add_argument("--margin", type=float, default=10.0, help="dB above noise floor = speech")
    p.add_argument("--min-db", type=float, default=-50.0, help="absolute minimum threshold")
    p.add_argument("--hangover-ms", type=int, default=700, help="silence that ends an utterance")
    p.add_argument("--preroll-ms", type=int, default=300)
    p.add_argument("--min-ms", type=int, default=400, help="ignore blips shorter than this")
    p.add_argument("--max-s", type=float, default=15.0)
    p.add_argument("--meter", action="store_true", help="print levels for tuning")
    args = p.parse_args()

    print(f"[stt] loading {args.model} on {args.device} ({args.compute})...")
    model = WhisperModel(args.model, device=args.device, compute_type=args.compute)
    jobs = queue.Queue()
    threading.Thread(target=transcriber, args=(model, jobs), daemon=True).start()

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", args.port))
    srv.listen(1)
    srv.settimeout(1.0)                  # lets Ctrl+C work on Windows
    print(f"[hub] listening on port {args.port}")
    try:
        while True:
            try:
                conn, addr = srv.accept()
            except socket.timeout:
                continue
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            handle_client(conn, addr, jobs, args)   # one ESP at a time
    except KeyboardInterrupt:
        print("\n[hub] bye")


if __name__ == "__main__":
    main()