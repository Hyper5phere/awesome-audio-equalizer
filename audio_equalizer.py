import numpy as np
import soundcard as sc

# get a list of all speakers:
speakers = sc.all_speakers()
# get the current default speaker on your system:
default_speaker = sc.default_speaker()

print(default_speaker)

num_channels = default_speaker.channels
sample_rate = 96000

# Create the multi channel noise array.
noise_samples = 5 * sample_rate
noise = np.random.uniform(-0.1, 0.1, noise_samples)
data = np.zeros((num_channels * noise_samples, num_channels), dtype=np.float32)
for channel in range(num_channels):
    data[channel * noise_samples:(channel + 1) * noise_samples, channel] = noise

with default_speaker.player(samplerate=sample_rate) as sp:
    sp.play(data)
