"""Generate the default ring sounds: timer_ring.wav and alarm_ring.wav.

The firmware plays a sound, waits for the gap set in packages/alarm.yaml, and
plays it again until the ringing is stopped.

    timer_ring.wav   four short beeps at one pitch
    alarm_ring.wav   three quick two-pitch beeps, higher and more urgent

Run from the repo folder (standard library only, nothing to install):

    .\\.venv\\Scripts\\python.exe firmware/satellite/sounds/make_ring.py

To use your own sound instead, you do not need this script: see
firmware/satellite/sounds/README.md.

Loudness: the files peak at PEAK of digital full scale. The speaker level cap
(hard rule 3) does not depend on these files; it is enforced by the media
player's volume_max in packages/audio.yaml, which scales every sound.
"""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

SAMPLE_RATE = 48_000  # matches the speaker, so the firmware does not resample
FADE_S = 0.008  # fade each beep in and out so it does not click
PEAK = 0.8

FOLDER = Path(__file__).parent

# A sound is a list of (pitch in Hz, seconds). A pitch of 0 is silence.
Pattern = list[tuple[float, float]]

# A6: clear on a small speaker and well away from speech.
TIMER: Pattern = [(1760.0, 0.09), (0.0, 0.09)] * 3 + [(1760.0, 0.09)]

# Two pitches back to back make each beep sound like "bee-beep".
ALARM: Pattern = ([(2093.0, 0.08), (2637.0, 0.10), (0.0, 0.10)] * 3)[:-1]


def tone(pitch_hz: float, seconds: float) -> list[float]:
    """One beep with a short fade at each end, or silence if the pitch is 0."""
    count = round(seconds * SAMPLE_RATE)
    if pitch_hz <= 0:
        return [0.0] * count
    fade = round(FADE_S * SAMPLE_RATE)
    samples: list[float] = []
    for n in range(count):
        envelope = min(1.0, n / fade, (count - 1 - n) / fade)
        samples.append(PEAK * envelope * math.sin(2 * math.pi * pitch_hz * n / SAMPLE_RATE))
    return samples


def build(pattern: Pattern) -> list[float]:
    samples: list[float] = []
    for pitch_hz, seconds in pattern:
        samples.extend(tone(pitch_hz, seconds))
    return samples


def write(name: str, pattern: Pattern) -> None:
    samples = build(pattern)
    path = FOLDER / name
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(b"".join(struct.pack("<h", round(s * 32767)) for s in samples))
    print(f"Wrote {path} ({len(samples) / SAMPLE_RATE:.2f} s, {path.stat().st_size} bytes)")


def main() -> None:
    write("timer_ring.wav", TIMER)
    write("alarm_ring.wav", ALARM)


if __name__ == "__main__":
    main()
