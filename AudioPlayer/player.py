import soundfile
import sounddevice as sd
import threading
import time
import numpy as np

# TODO Add pitch and time shifting
# TODO Add custom dithering

# wav_path = "Z:\\SFX Library\\SoundDogs\\" \
# 			"Humvee, Onb,55 MPH,Start Idle Revs,Drive Fast,Uphill Accelerate H,6003_966817.wav"
# normal = "Z:\\SFX Library\\SoundDogs\\M4 Grenade Launcher,Shots,Single x3 Double
# x1 Burst x20,C-Hard Mi,7242_966594.wav"
# wav_96k = "Z:\\SFX Library\\SoundDogs\\" \
# 			"Humvee M998,Pavement,50 MPH,Pass Bys x2 Med Fast,Approach Pothole,5954_966759.wav"
# mp3_path = "Z:\\SFX Library\\ProSound\\2013 Flying Proms Junkers Ju 52 flight.mp3"
# count_path = "Z:\\SFX Library\\Digital Juice\\Digital Juice Files\\SFX_V01D07D\\Human\\OnTheSet\\" \
# 				"Check One, Two, Three Testing.Wav"
# ogg_path = "Z:\\SFX Library\\Digital Juice\\Digital Juice Files\\SFX_V03D01D_V2\\General\\Transportation\\" \
# 			"Train By 2.Ogg"
# flac_path = "C:\\Users\\Josh\\Downloads\\455746__kyles__door-apartment-buzzer-unlock-ext.flac"


class Player:
	def __init__(self):
		self.audio_buffer = AudioBuffer(self.end)
		self.audio_buffer_thread = threading.Thread(target=self.audio_buffer.buffer_loop)
		self.audio_buffer_thread.start()
		self.audio_player = AudioThread(self.audio_buffer.ready)
		self.audio_player_thread = threading.Thread(target=self.audio_player.run_loop)
		self.audio_player_thread.start()
		self.playing = False
		self.paused = False
		self.ended = False
		self.started = False

	def load(self, path):
		self.audio_buffer.load(path)
		self.audio_buffer.processes = self.audio_buffer.get_processes()
		self.audio_buffer.CHUNK_SIZE = self.audio_buffer.get_recommended_chunk_size()
		self.audio_player.load(self.audio_buffer.sound_info.samplerate, self.audio_buffer.CHUNK_SIZE,
								self.audio_buffer.channels, self.audio_buffer.get_buffer)

	@property
	def selected_channels(self):
		return self.audio_buffer.PLAY_INDIVIDUAL_CHANNELS

	@selected_channels.setter
	def selected_channels(self, value: list):
		self.audio_buffer.PLAY_INDIVIDUAL_CHANNELS = value

	@property
	def sum_to_mono(self):
		return self.audio_buffer.SUM_TO_MONO

	@sum_to_mono.setter
	def sum_to_mono(self, value: bool):
		self.audio_buffer.SUM_TO_MONO = value

	@property
	def chunk_size(self):
		return self.audio_buffer.CHUNK_SIZE

	@chunk_size.setter
	def chunk_size(self, value: int):
		self.audio_buffer.CHUNK_SIZE = value

	def determine_summing_policy(self):
		if self.audio_buffer.sound_info.channels > 2:
			self.audio_buffer.SUM_TO_MONO = True
		else:
			self.audio_buffer.SUM_TO_MONO = False

	def end(self):
		self.ended = True
		raise sd.CallbackStop

	def play(self):
		self.audio_player.play()
		self.playing = True

	def pause(self):
		self.audio_player.pause()
		self.paused = True

	def stop(self):
		self.playing = False

	def goto(self, goto):
		self.audio_player.pause()
		self.audio_buffer.seek(goto)
		if self.playing and not self.paused:
			self.play()


class AudioBuffer:
	SUM_TO_MONO = False
	PLAY_INDIVIDUAL_CHANNELS = []
	PITCH_SHIFT = 0
	TIME_SHIFT = 0
	CHUNK_SIZE = 1024

	def __init__(self, end_callback):
		self.end_callback = end_callback
		self.sound_file = None
		self.buffer = []
		self.path = None
		self.sound_info = None
		self.finished = False
		self.loaded = False
		self.processes = []

	@property
	def channels(self):
		if self.SUM_TO_MONO or self.sound_info.channels == 1:
			return 1
		return 2

	def ready(self):
		return len(self.buffer) > 0

	def buffer_loop(self):
		while True:
			while self.sound_file:
				self.set_buffer()
				self.loaded = True
			time.sleep(.03)

	def load(self, path):
		self.finished = False
		self.path = path
		self.sound_file = soundfile.SoundFile(path)
		self.sound_info = soundfile.info(path)

	def set_buffer(self):
		if len(self.buffer) < 50 and not self.finished:
			data = self.get_correct_amount_of_channels(self.get_selected_channels(self.sound_file.read(self.CHUNK_SIZE)))
			data = self.pad_sound(data)
			self.buffer.append(self.run_data_through_processes(data, self.processes))

	def seek(self, goto):
		"""
		Set read from frame
		:param goto:
			should be in milliseconds
		"""
		goto_frame = int(self.sound_info.samplerate * (goto / 1000))
		self.buffer = []
		try:
			self.sound_file.seek(goto_frame)
		except RuntimeError:
			self.sound_file.seek(self.sound_info.frames-1)

	def pad_sound(self, data):
		data_chunk_size = data.shape[0]
		if 0 < data_chunk_size < self.CHUNK_SIZE:
			data = np.pad(data, [(0, self.CHUNK_SIZE - data_chunk_size), (0, 0)], mode='constant')
			self.finished = True
		return data

	def get_recommended_chunk_size(self):
		"""Make sure to set processes first"""
		chunk_size = 1024
		if self.sound_info.channels > 2:
			chunk_size += 1024 * (self.sound_info.channels - 2)
		if len(self.PLAY_INDIVIDUAL_CHANNELS) > 0:
			chunk_size += 1024
		return chunk_size

	def get_buffer(self, outdata, frames, time, status):
		outdata[:] = self.buffer.pop(0)
		if self.finished and len(self.buffer) == 0:
			self.end_callback()

	@staticmethod
	def run_data_through_processes(data, processes):
		for process in processes:
			data = process(data)
		return data

	def get_processes(self):
		processes = []
		return processes

	def get_correct_amount_of_channels(self, data):
		try:
			if data.shape[1] > 2 or self.SUM_TO_MONO or len(self.PLAY_INDIVIDUAL_CHANNELS) > 0:
				return self.sum_to_mono(data)
		except IndexError:
			return np.ndarray(buffer=data, shape=(data.shape[0], 1))
		return data

	def sum_to_mono(self, data):
		sound_data = np.ndarray(buffer=np.average(data, axis=1), shape=(data.shape[0], 1))
		return sound_data

	def get_selected_channels(self, data):
		if len(self.PLAY_INDIVIDUAL_CHANNELS) > 0:
			return self._get_selected_channels_from_play_channels(data)
		return data

	def _get_selected_channels_from_play_channels(self, data):
		channels = self.get_individual_channels(data)
		selected_channels = np.ndarray((data.shape[0], 0))
		for channel_number in self.PLAY_INDIVIDUAL_CHANNELS:
			try:
				selected_channels = np.concatenate((selected_channels, channels[channel_number-1]), axis=1)
			except IndexError:
				continue
		return selected_channels

	@staticmethod
	def get_individual_channels(data):
		sound_data = np.hsplit(data, data.shape[1])
		return sound_data


class AudioThread:
	def __init__(self, ready_callback):
		self.ready_callback = ready_callback
		self.stream = None
		self.should_start = False
		self.should_stop = False

	def load(self, sample_rate, block, channels, callback):
		self.reset()
		self.stream = sd.OutputStream(samplerate=sample_rate, blocksize=block, channels=channels, callback=callback)

	def reset(self):
		try:
			self.stream.close()
		except AttributeError:
			pass

	def play(self):
		self.should_start = True

	def pause(self):
		self.stream.stop()

	def run_loop(self):
		while True:
			if self.should_start and self.ready_callback():
				self.stream.start()
				self.should_start = False
			time.sleep(.005)


# p = WavPlayer()
# p.load(wav_path)
# while not p.audio_buffer.loaded:
# 	time.sleep(.001)
# p.play()
# time.sleep(2)
# # p.goto(10000)
#
# while True:
# 	time.sleep(1)
