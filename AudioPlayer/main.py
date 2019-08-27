import soundfile
import sounddevice as sd
import threading
import time
import numpy as np

wav_path = "Z:\\SFX Library\\SoundDogs\\" \
			"Humvee, Onb,55 MPH,Start Idle Revs,Drive Fast,Uphill Accelerate H,6003_966817.wav"
normal = "Z:\\SFX Library\\SoundDogs\\M4 Grenade Launcher,Shots,Single x3 Double x1 Burst x20,C-Hard Mi,7242_966594.wav"
wav_96k = "Z:\\SFX Library\\SoundDogs\\" \
			"Humvee M998,Pavement,50 MPH,Pass Bys x2 Med Fast,Approach Pothole,5954_966759.wav"
mp3_path = "Z:\\SFX Library\\ProSound\\2013 Flying Proms Junkers Ju 52 flight.mp3"
count_path = "Z:\\SFX Library\\Digital Juice\\Digital Juice Files\\SFX_V01D07D\\Human\\OnTheSet\\" \
				"Check One, Two, Three Testing.Wav"
BLOCK_SIZE = 1024


def try_to_check_if_none(value):
	try:
		if not value:
			return True
		else:
			return False
	except ValueError:
		return False


# sr = soundfile.info(wav_path).samplerate
# start = time.time()
# data_array = None
# for block in soundfile.blocks(wav_path, BLOCK_SIZE, 0):
# 	if block.shape[1] > 2:
# 		block = block.flatten()
	# 	print(block)
	# if try_to_check_if_none(data_array):
	# 	data_array = block
	# else:
	# 	data_array = np.append(data_array, block)
	# print('test')
# start = time.time()
# data, sample_rate = soundfile.read(wav_path)
# print(data)
# data = np.ndarray.flatten(data)
# data.sum(axis=1)/2
# sd.play(data, sample_rate)

class WavPlayer:
	def __init__(self):
		self.audio_player = AudioThread()
		self.audio_player_thread = threading.Thread(target=self.audio_player.run_loop)
		self.audio_player_thread.start()
		self.audio_buffer = AudioBuffer(self.end)
		self.audio_buffer_thread = threading.Thread(target=self.audio_buffer.buffer_loop)
		self.audio_buffer_thread.start()
		self.playing = False
		self.paused = False
		self.ended = False
		self.started = False

	def load(self, path):
		self.audio_buffer.load(path)
		self.determine_summing_policy()
		self.audio_buffer.processes = self.audio_buffer.get_processes()
		self.audio_buffer.CHUNK_SIZE = self.audio_buffer.get_recommended_chunk_size()
		self.audio_player.load(self.audio_buffer.sound_info.samplerate, self.audio_buffer.CHUNK_SIZE,
								self.audio_buffer.channels, self.audio_buffer.get_buffer)

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
	PLAY_INDIVIDUAL_CHANNEL = 0
	PITCH_SHIFT = 0
	TIME_SHIFT = 0
	CHUNK_SIZE = 5024

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
			print(len(self.buffer))
			data = self.pad_sound(self.sound_file.read(self.CHUNK_SIZE))
			self.buffer.append(self.run_data_through_processes(data, self.processes))

	def seek(self, goto):
		"""
		Set read from frame
		:param goto:
			should be in milliseconds
		"""
		goto_frame = int(self.sound_info.samplerate * (goto / 1000))
		self.buffer = []
		print(goto_frame)
		self.sound_file.seek(goto_frame)

	def pad_sound(self, data):
		data_chunk_size = data.shape[0]
		if 0 < data_chunk_size < self.CHUNK_SIZE:
			data = np.pad(data, [(0, self.CHUNK_SIZE - data_chunk_size), (0, 0)], mode='constant')
			self.finished = True
		return data

	def get_recommended_chunk_size(self):
		"""Make sure to set processes first"""
		chunk_size = 5120
		if self.sound_info.channels > 2:
			chunk_size += 1024 * (self.sound_info.channels - 2)
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
		if self.PLAY_INDIVIDUAL_CHANNEL > 0:
			processes.append(self.get_individual_channel)
		if self.SUM_TO_MONO:
			processes.append(self.sum_to_mono)
		return processes

	def sum_to_mono(self, data):
		sound_data = np.ndarray(buffer=np.average(data, axis=1), shape=(self.CHUNK_SIZE, 1))
		return sound_data

	def get_individual_channel(self, data):
		return self.get_individual_channels(data)[self.PLAY_INDIVIDUAL_CHANNEL-1]

	@staticmethod
	def get_individual_channels(data):
		sound_data = np.hsplit(data, data.shape[1])
		return sound_data


class AudioThread:
	def __init__(self):
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
		print('play')
		self.should_start = True

	def pause(self):
		self.should_stop = True

	def run_loop(self):
		while True:
			if self.should_start:
				self.stream.start()
				self.should_start = False
			elif self.should_stop:
				self.stream.stop()
				self.should_stop = False
			time.sleep(.01)


p = WavPlayer()
p.load(wav_path)
while not p.audio_buffer.loaded:
	time.sleep(.001)
p.play()
time.sleep(2)
p.goto(10000)
p.play()

while True:
	time.sleep(1)
