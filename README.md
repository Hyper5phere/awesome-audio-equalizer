# Audio Equalizer Program in Python

Applies audio equalizer to all sound of your default audio output (speaker or headset)

## Setup

Recommended way to use this software is to first install a virtual audio cable from here: https://vb-audio.com/Cable/index.htm

Then install python and run 

```bash
pip install -r requirements.txt
```

Then you need to select your real audio device, and write its name to `config.ini` file, e.g.,

```ini
output_speaker_name=Digital Audio (S/PDIF)
```

Then just run the the `audio_equalizer.bat`
