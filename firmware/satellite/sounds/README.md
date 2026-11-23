# Satellite sounds

Sounds in this folder are built into the firmware, so they play with no network.

| File | Used for |
|---|---|
| `timer_ring.wav` | The ring when a timer finishes. Four short beeps, made by `make_ring.py`. |
| `make_ring.py` | Generates `timer_ring.wav`. Standard-library Python, nothing to install. |

## Using your own ring sound
1. Put your file in this folder. WAV, FLAC or MP3 all work. Keep it short (a few seconds): the
   firmware repeats it, and the pause between repeats is when the hub can hear "stop".
2. In `firmware/satellite/packages/alarm.yaml`, change one line at the top:

       ring_sound_file: sounds/your-file.wav

3. Optionally change `ring_gap` on the next line, the silence between repeats.
4. Compile and flash as usual.

The file's own loudness does not affect the speaker level cap. The cap is enforced by the media
player (`volume_max` in `packages/audio.yaml`), which scales every sound.

To change the built-in beeps instead, edit the numbers at the top of `make_ring.py` and run it again:

    .\.venv\Scripts\python.exe firmware/satellite/sounds/make_ring.py
