'''
Audio Equalizer application that processes audio stream coming
from an input audio device and streams the filtered signal
to an output device. Requires 

Uses multiple processes, threads and vectorized operations in
an serious attempt to maximize audio throughput and minimize latency.
This application can be somewhat heavy on your CPU though, I'm 
probably doing something wrong as I'm no audio processing expert.
Also the audio quality might not be the best. But this is just a 
hobby project, so use it at your own risk :D

Author: Hyper5phere
Github: https://github.com/Hyper5phere
Date: 13.10.2024
'''

import time
import logging
import configparser
import tkinter as tk
from typing import List
from threading import Thread
from queue import Empty, Full
from multiprocessing import Process, Queue, Value, Pool, Array

import numpy as np
import soundcard as sc
from scipy.signal import butter, lfilter


def play_task(playing: bool, audio_queue: Queue,
              sample_rate: int, block_size: int,
              sp_name_arr: List[int]) -> None:
    '''
    Player child process, it simply fetches data from intel queue and plays it
    in the selected output speaker. Looks slightly ugly because of Python
    multiprocessing library restrictions.
    '''
    speakers = sc.all_speakers()
    # Seriously, this is the most complicated way to pass a string variable
    # to a function that I've ever wrote... but hey it works!
    output_speaker_name = "".join(chr(c) for c in sp_name_arr[:])
    try:
        # let's not be too picky about casing or surrounding whitespace...
        output_sp_name = output_speaker_name.lower().strip()
        speaker = next(s for s in speakers if output_sp_name in s.name.lower())
    except StopIteration:
        raise ValueError(f'The selected input audio device "{output_speaker_name}" '
                         'not found on the system!')
    with speaker.player(samplerate=sample_rate.value, blocksize=block_size.value) as sp:
        while playing.value:
            try:
                data = audio_queue.get_nowait()
                if np.any(data):
                    sp.play(data)
                else:
                    # nothing to play here so I sleep...
                    time.sleep(0.01)
            except Empty:
                time.sleep(0.0001)


def apply_band_filter(b: np.ndarray, a: np.ndarray,
                      data: np.ndarray, gain: float):
    ''' The most performance critical operation of this program,
    can be run in parallel in many child processes. Applies a
    filter on the selected frequency band. '''
    return lfilter(b, a, data, axis=0) * (10 ** (gain/20))


class AudioEqualizerGUI:
    '''
    Tkinter GUI application for equalizing audio stream coming
    from an input audio device and streaming the filtered signal
    to output device. Requires `config.ini` file to exist in the
    application folder to load app configurations.
    '''
    def __init__(self, master: tk.Tk):
        # Tkinter master window
        self.master = master

        # UI parameters
        self.button_width = 30
        self.window_width = 1400
        self.window_height = 540

        # Init Tkinter GUI window
        master.title("Awesome Audio Equalizer")
        master.geometry(f"{self.window_width}x{self.window_height}")

        self.logger = logging.getLogger("awesome.audio.equalizer")

        # which frequency bands to apply filters to
        self.freq_bands = [
            (20, 76),
            (77, 109),
            (110, 155),
            (156, 219),
            (220, 310),
            (311, 439),
            (440, 621),
            (622, 879),
            (880, 1200),
            (1201, 1800),
            (1801, 2500),
            (2501, 3499),
            (3500, 5000),
            (5001, 7000),
            (7001, 10000),
            (10001, 14000),
            (14001, 18000),
            (18001, 20000)
        ]

        self.config = configparser.ConfigParser()
        if not self.config.read('config.ini'):
            raise AssertionError("Missing config.ini file in app directory!")
        try:
            self.config = self.config["Equalizer_Configuration"]

            # Input and output device definitions
            self.input_speaker_name = self.config["input_device_name"]
            self.output_speaker_name = self.config["output_device_name"]

            self.block_size = int(self.config["block_size"])
            self.record_size = self.block_size * 4
            self.sample_rate = int(self.config["sample_rate"])
            self.volume = float(self.config["initial_volume"])
        except KeyError as kerr:
            raise KeyError(f"Missing configuration parameter: {kerr}")
        except ValueError as verr:
            raise ValueError(f"Invalid configuration parameter value: {verr}")

        # Internal equalizer parameters
        self._filters = self._design_filters()
        self._gains = [0] * len(self.freq_bands)  # initial gains at zero

        self.audio_queue = Queue(maxsize=self.config.getint("max_queue_size"))
        self.num_dsp_processes = self.config.getint("num_dsp_processes")
        self.player = None
        self.listener = None

        # Shared memory variables to used between child processes that support atomic operations
        self.sample_rate_shared = Value('i', self.sample_rate)
        self.block_size_shared = Value('i', self.block_size)
        self.output_speaker_name_shared = self._encode_shared_string(self.output_speaker_name)

        # Control flags for threads and processes
        self.applying = False
        self.playing = Value('b', True)

        mics = sc.all_microphones(include_loopback=True)
        try:
            # let's not be too picky about casing or surrounding whitespace...
            input_sp_name = self.input_speaker_name.lower().strip()
            self.loopback_mic = next(m for m in mics if input_sp_name in m.name.lower())
        except StopIteration:
            raise ValueError(f'The selected input audio device "{self.input_speaker_name}" '
                             'not found on the system!')
        
        self.logger.info("Listening to audio output: %s", self.loopback_mic.name)
        
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
    

    def _encode_shared_string(self, str_var: str):
        return Array('i', [ord(c) for c in str_var])

    
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

        # TODO: implement saving presets?
        # # Load Button
        # self.load_button = tk.Button(self.button_frame, text="Load Configuration", width=20, bg="lightblue")
        # self.load_button.pack(pady=10)
        
        # # Save Button
        # self.save_button = tk.Button(self.button_frame, text="Save Configuration", width=20, bg="lightgreen")
        # self.save_button.pack(pady=10)
        
        # Status Label
        self.status_label = tk.Label(self.master, text="Equalizer not applied", fg="blue", font=("Helvetica", 12))
        self.status_label.pack(pady=5)

        self.vol_slider = tk.Scale(self.master, from_=0, to=200, orient=tk.HORIZONTAL, resolution=1, length=int(self.window_width * 0.9),
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
        self._gains[band_index] = gain_db
        l, h = self.freq_bands[band_index]
        self.status_label.config(text=f"Updated {(l + h) // 2} Hz Gain to {gain_db} dB", fg="blue")


    def reset_gains(self):
        self.logger.info("Resetting equalizer band gains...")
        self._gains = [0] * len(self.freq_bands)
        for slider in self.sliders:
            slider.set(0)
        self.status_label.config(text="Reset band gains", fg="blue")


    def quit(self):
        self.logger.info("Exiting...")
        self.playing.value = False
        self.applying = False
        # using join() here can result in the app hanging indefinitely,
        # so we just give the workers some time to cleanup
        time.sleep(1)
        self.master.quit()

    
    def toggle_equalizer(self):
        self.applying = not self.applying
        if self.applying:
            self.listener = Thread(target=self.listen, daemon=True)
            self.listener.start()
            self.process_button.config(relief="sunken", text="Disable Equalizer", bg="lightgreen", fg="black")
            self.status_label.config(text="Equalizer enabled", fg="blue")
            self.logger.info("Equalizer enabled")
        else:
            self.listener.join()
            self.process_button.config(relief="raised", text="Enable Equalizer", bg="green", fg="white")
            self.status_label.config(text="Equalizer disabled", fg="blue")
            self.logger.info("Equalizer disabled")
                             

    def _equalize(self, data, pool):
        filter_inputs = []
        for gain, (b, a) in zip(self._gains, self._filters):
            filter_inputs.append((b, a, data, gain))
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
        self.output_speaker_name_shared = self._encode_shared_string(self.output_speaker_name)
        self.player = Process(target=play_task,
                              daemon=True,
                              args=(self.playing, self.audio_queue,
                                    self.sample_rate_shared,
                                    self.block_size_shared,
                                    self.output_speaker_name_shared))
        self.player.start()


    def listen(self):
        with self.loopback_mic.recorder(samplerate=self.sample_rate,
                                        blocksize=self.block_size) as mic:
            with Pool(self.num_dsp_processes) as pool:
                try:
                    self.start_player()
                    while self.applying:
                        recorded_data = mic.record(self.record_size)
                        if np.any(recorded_data):
                            equalized_data = self._equalize(recorded_data * self.volume, pool)
                            try:
                                self.audio_queue.put_nowait(equalized_data)
                            except Full:
                                self.logger.warning("Internal audio buffer overflow, dropping audio block...")
                        else:
                            time.sleep(0.01)
                finally:
                    self.playing.value = False
                    try:
                        self.player.join()
                    except AssertionError:
                        # just catch an unhelpful and ugly error message:
                        # AssertionError: can only join a started process
                        pass


def main():
    root = tk.Tk()
    app = AudioEqualizerGUI(root)
    root.mainloop()


if __name__ == '__main__':
    logging.basicConfig(
        level="INFO",
        format='%(asctime)s :: %(levelname)-8s :: %(name)-25s :: %(relativeCreated)6d ms :: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S')
    main()
