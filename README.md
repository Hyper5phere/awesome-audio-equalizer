# Awesome Audio Equalizer

Applies audio equalizer and volume control to all sound of your default audio output device (speaker or headset).

## Setup

The recommended way to use this software is to first install a virtual audio cable from here: https://vb-audio.com/Cable/index.htm

Then install python and dependencies. 

```bash
pip install -r requirements.txt
```

Then you need to select your real audio device, and write its name to `config.ini` file, e.g.,

```ini
output_speaker_name=Digital Audio (S/PDIF)
```

Then just run the the `audio_equalizer.bat`. Enjoy!

## Troubleshooting

### Help, my audio sounds horrible or has terrible latency!

Try playing around with the `config.ini` settings:

```ini
sample_rate=48000    # trade-off between sound quality and processing speed
block_size=8192      # this is similar, it affects latency a lot
num_dsp_processes=2  # you can ramp up this number if you have CPU cores to spare
max_queue_size=10    # This affects overall app responsiveness
```
Use reasonable numbers (i.e., positive integers) and test one parameter at a time whether it improves performance and/or sound quality. Although these are already reasonable default values so I advice not to change them too drastically. Remember, you need to restart the app for your changes to take effect!
