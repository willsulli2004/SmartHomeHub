"""Generate the default timer ring sound, timer_ring.wav.

The sound is four short beeps. The firmware plays it, waits for the gap set in
packages/alarm.yaml, and plays it again until the ringing is stopped.

Run from the repo folder (standard library only, nothing to install):

    .\\.venv\\Scripts\\python.exe firmware/satellite/sounds/make_ring.py

To use your own sound instead, you do not need this script: see
firmware/satellite/sounds/README.md.

Loudness: the file peaks at PEAK of digital full scale. The speaker level cap
(hard rule 3) does not depend on this file; it is enforced by the media player's
volume_max in packages/audio.yaml, which scales every sound.
"""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

SAMPLE_RATE = 48_000  # matches the speaker, so the firmware does not resample
TONE_HZ = 1_760.0  # A6: clear on a small speaker, well away from speech
BEEPS = 4
BEEP_S = 0.09
PAUSE_S = 0.09
FADE_S = 0.008  # fade each beep in and out so it does not click
PEAK = 0.8

OUTPUT = Path(__file__).with_name("timer_ring.wav")


def beep() -> list[float]:
    """One beep with a short fade at each end."""
    count = round(BEEP_S * SAMPLE_RATE)
    fade = round(FADE_S * SAMPLE_RATE)
    samples: list[float] = []
    for n in range(count):
        envelope = min(1.0, n / fade, (count - 1 - n) / fade)
        samples.append(PEAK * envelope * math.sin(2 * math.pi * TONE_HZ * n / SAMPLE_RATE))
    return samples


def build() -> list[float]:
    """The whole sound: BEEPS beeps separated by short pauses."""
    pause = [0.0] * round(PAUSE_S * SAMPLE_RATE)
    samples: list[float] = []
    for index in range(BEEPS):
        samples.extend(beep())
        if index < BEEPS - 1:
            samples.extend(pause)
    return samples


def main() -> None:
    samples = build()
    with wave.open(str(OUTPUT), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(b"".join(struct.pack("<h", round(s * 32767)) for s in samples))
    print(f"Wrote {OUTPUT} ({len(samples) / SAMPLE_RATE:.2f} s, {OUTPUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
