import os
import time
import numpy as np
import soundcard as sc
import tkinter as tk
import configparser
from threading import Thread
from queue import Empty
from scipy.signal import butter, lfilter

from multiprocessing import Process, Queue, Value, Pool

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))


def play_task(playing, audio_queue, sample_rate, block_size):
    # output_speaker_name = "BenQ GW2765"
    output_speaker_name = "Digital Audio (S/PDIF)"
    speakers = sc.all_speakers()
    speaker = next(s for s in speakers if output_speaker_name in s.name)
    with speaker.player(samplerate=sample_rate.value, blocksize=block_size.value) as sp:
        while playing.value:
            try:
                data = audio_queue.get_nowait()
                sp.play(data)
            except Empty:
                time.sleep(0.00001)


def apply_band_filter(b, a, data, gain):
    return lfilter(b, a, data, axis=0) * (10 ** (gain/20))

class AudioEqualizerGUI:
    def __init__(self, master):
        self.master = master
        self.window_width = 1400
        self.window_height = 540
        master.title("Awesome Audio Equalizer")
        master.geometry(f"{self.window_width}x{self.window_height}")

        self.freq_bands = [
            (40, 76),
            (77, 109),
            (110, 155),
            (156, 219),
            (220, 310),
            (311, 439),
            (440, 621),
            (622, 879),
            (880, 1199),
            (1200, 1799),
            (1800, 2499),
            (2500, 3499),
            (3500, 4999),
            (5000, 6999),
            (7000, 9999),
            (10000, 13999),
            (14000, 17999),
            (18000, 20000)
        ]

        self.config = configparser.ConfigParser()
        self.config.read(os.path.join(SCRIPT_DIR, 'config.ini'))
        self.config = self.config["Equalizer_Configuration"]

        self.block_size = self.config.getint("block_size")
        self.input_speaker_name = self.config["input_speaker_name"]
        self.record_size = self.block_size * 4
        self.sample_rate = self.config.getint("sample_rate")
        self.volume = self.config.getfloat("initial_volume")
        self.filters = self._design_filters()
        self.gains = [0] * len(self.freq_bands)  # initial gains at zero
        # self.gains = [10, 8, 6, 4, 3, 2, 1, 0, 1, 2, 3, 4, 5, 6, 6, 6, 6, 6]
        self.button_width = 30

        self.audio_queue = Queue()
        self.num_dsp_processes = self.config.getint("num_dsp_processes")
        self.playing = Value('b', True)
        self.sample_rate_shared = Value('i', self.sample_rate)
        self.block_size_shared = Value('i', self.block_size)
        self.player = None
        self.listener = None

        mics = sc.all_microphones(include_loopback=True)
        self.loopback_mic = next(m for m in mics if self.input_speaker_name in m.name)
        self.applying = False
        
        # Create UI elements
        self.create_widgets()


    def _design_filters(self, order=2):
        filters = []
        nyq = 0.5 * self.sample_rate
        for lowcut, highcut in self.freq_bands:
            low = lowcut / nyq
            high = highcut / nyq
            filters.append(butter(order, [low, high], btype='bandpass'))
        return filters

    
    def create_widgets(self):
        
        # Frame for sliders
        self.sliders_frame = tk.Frame(self.master)
        self.sliders_frame.pack(fill=tk.Y, pady=10)
        
        # Labels and sliders for each band
        self.slider_labels = []
        self.sliders = []
        for i, (low, high) in enumerate(self.freq_bands):
            
            slider = tk.Scale(self.sliders_frame, from_=20, to=-20, orient=tk.VERTICAL, resolution=0.1, length=300,
                              command=lambda val, idx=i: self.update_gain(idx, float(val)), width=15)
            slider.set(0)
            slider.grid(column=i, row=0, padx=0, pady=2)
            label = tk.Label(self.sliders_frame, text=f"{(high + low) // 2} Hz", width=8, font=("Helvetica", 10), anchor="e")
            label.grid(column=i, row=1, padx=0, pady=2)
            self.slider_labels.append(label)
            self.sliders.append(slider)

        self.button_frame = tk.Frame(self.master)
        self.button_frame.pack(fill=tk.Y, pady=10)
        
        # Process Button
        self.process_button = tk.Button(self.button_frame, text="Enable Equalizer",
                                        command=self.toggle_equalizer, bg="green",
                                        fg="white", relief="raised", width=self.button_width)
        self.process_button.grid(column=0, row=0, padx=10, pady=2)

        # Reset Button
        self.exit_button = tk.Button(self.button_frame, text="Reset", command=self.reset_gains,
                                     bg="orange", fg="white", width=self.button_width)
        self.exit_button.grid(column=1, row=0, padx=10, pady=2)

        # Exit Button
        self.exit_button = tk.Button(self.button_frame, text="Exit", command=self.quit,
                                     bg="red", fg="white", width=self.button_width)
        self.exit_button.grid(column=2, row=0, padx=10, pady=2)

        # # Load Button
        # self.load_button = tk.Button(self.button_frame, text="Load Configuration", width=20, bg="lightblue")
        # self.load_button.pack(pady=10)
        
        # # Save Button
        # self.save_button = tk.Button(self.button_frame, text="Save Configuration", width=20, bg="lightgreen")
        # self.save_button.pack(pady=10)
        
        # Status Label
        self.status_label = tk.Label(self.master, text="Equalizer not applied", fg="blue", font=("Helvetica", 12))
        self.status_label.pack(pady=5)

        self.vol_slider = tk.Scale(self.master, from_=0, to=100, orient=tk.HORIZONTAL, resolution=1, length=int(self.window_width * 0.9),
                                   command=self.update_volume)
        self.vol_slider.pack(pady=2)
        self.vol_slider.set(int(self.volume * 100))
        self.vol_label = tk.Label(self.master, text="Master Volume", font=("Helvetica", 12))
        self.vol_label.pack(pady=5)
        
        
    def update_volume(self, volume):
        self.volume = int(volume) / 100.
        self.status_label.config(text=f"Updated volume to {volume} %", fg="blue")


    def update_gain(self, band_index, gain_db):
        """
        Update the gain for a specific frequency band.
        """
        self.gains[band_index] = gain_db
        self.status_label.config(text=f"Updated {self.freq_bands[band_index][0]} Hz Gain to {gain_db} dB", fg="blue")


    def reset_gains(self):
        self.gains = [0] * len(self.freq_bands)
        for slider in self.sliders:
            slider.set(0)
        self.status_label.config(text="Reset band gains", fg="blue")


    def quit(self):
        self.playing.value = False
        if self.applying:
            self.applying = False
            self.listener.join()
        self.master.quit()

    
    def toggle_equalizer(self):
        self.applying = not self.applying
        if self.applying:
            self.listener = Thread(target=self.listen)
            self.listener.start()
            self.process_button.config(relief="sunken", text="Disable Equalizer", bg="lightgreen", fg="black")
            self.status_label.config(text="Equalizer enabled", fg="blue")
        else:
            self.listener.join()
            self.process_button.config(relief="raised", text="Enable Equalizer", bg="green", fg="white")
            self.status_label.config(text="Equalizer disabled", fg="blue")


    def _equalize(self, data, pool):
        filter_inputs = []
        # band_list = []
        for gain, (b, a) in zip(self.gains, self.filters):
            filter_inputs.append((b, a, data, gain))
            # band_list.append(lfilter(b, a, data, axis=0) * (10 ** (gain/20)))
        band_list = pool.starmap(apply_band_filter, filter_inputs)
        signal = np.sum(band_list, axis=0)
        # Normalize to prevent clipping
        max_val = np.max(np.abs(signal))
        if max_val > 1:
            signal /= max_val
        return signal
    

    def start_player(self):
        self.playing = Value('b', True)
        self.sample_rate_shared = Value('i', self.sample_rate)
        self.block_size_shared = Value('i', self.block_size)
        self.player = Process(target=play_task,
                              args=(self.playing, self.audio_queue,
                                    self.sample_rate_shared,
                                    self.block_size_shared))
        self.player.start()


    def listen(self):
        with self.loopback_mic.recorder(samplerate=self.sample_rate,
                                        blocksize=self.block_size) as mic:
            with Pool(self.num_dsp_processes) as pool:
                try:
                    self.start_player()
                    while self.applying:
                        recorded = mic.record(self.record_size)
                        volume_adjusted = recorded * self.volume
                        equalized = self._equalize(volume_adjusted, pool)
                        self.audio_queue.put(equalized)
                finally:
                    self.playing.value = False
                    self.player.join()
    

def main():
    root = tk.Tk()
    app = AudioEqualizerGUI(root)
    root.mainloop()


if __name__ == '__main__':
    main()
