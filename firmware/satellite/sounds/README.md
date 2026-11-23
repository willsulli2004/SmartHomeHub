# Satellite sounds

Sounds in this folder are built into the firmware, so they play with no network.

| File | Used for |
|---|---|
| `timer_ring.wav` | The ring when a timer finishes. Four short beeps. |
| `alarm_ring.wav` | The ring when an alarm goes off. Three quick two-pitch beeps. |
| `make_ring.py` | Generates both files. Standard-library Python, nothing to install. |

## Using your own sound
1. Put your file in this folder. WAV, FLAC or MP3 all work. Keep it short (a few seconds): the
   firmware repeats it, and the pause between repeats is when the hub can hear "stop".
2. In `firmware/satellite/packages/alarm.yaml`, change one line at the top:

       timer_sound_file: sounds/your-file.wav

   or, for the alarm:

       alarm_sound_file: sounds/your-file.wav

3. Optionally change `ring_gap` a few lines below, the silence between repeats.
4. Compile and flash as usual.

A sound is part of the firmware, so changing it needs a flash. The ringing volumes, colours and the
timer's timeout do not: they are settings on the Satellite Hub device page in Home Assistant.

The file's own loudness does not affect the speaker level cap. The cap is enforced by the media
player (`volume_max` in `packages/audio.yaml`), which scales every sound.

To change the built-in beeps instead, edit the patterns at the top of `make_ring.py` and run it again:

    .\.venv\Scripts\python.exe firmware/satellite/sounds/make_ring.py
