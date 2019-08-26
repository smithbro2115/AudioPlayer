import soundfile
import sounddevice as sd
import threading
import time
import numpy as np

wav_path = "C:\\Users\\smith\\Downloads\\Sounddogs_Order\\" \
			"Humvee, Onb,55 MPH,Start Idle Revs,Drive Fast,Uphill Accelerate H,6003_966817.wav"
normal = "C:\\Users\\smith\\Downloads\\Sounddogs_Order\\Humvee Door O C_808671.wav"
wav_96k = "Z:\\SFX Library\\SoundDogs\\" \
			"Humvee M998,Pavement,50 MPH,Pass Bys x2 Med Fast,Approach Pothole,5954_966759.wav"
mp3_path = "Z:\\SFX Library\\ProSound\\2013 Flying Proms Junkers Ju 52 flight.mp3"
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
		self.audio_buffer = AudioBuffer()
		self.audio_buffer_thread = threading.Thread(target=self.audio_buffer.buffer_loop)
		self.audio_buffer_thread.start()
		self.playing = False
		self.paused = False
		self.ended = False
		self.started = False

	def load(self, path):
		self.audio_buffer.load(path)
		self.audio_player.load(self.audio_buffer.sound_info.samplerate, self.audio_buffer.CHUNK_SIZE,
								self.audio_buffer.get_buffer)

	def play(self):
		self.audio_player.play()
		self.playing = True

	def pause(self):
		self.audio_player.pause()
		self.playing = False
		self.paused = True


class AudioBuffer:
	SUM_TO_MONO = False
	PLAY_INDIVIDUAL_CHANNEL = 0
	PITCH_SHIFT = 0
	TIME_SHIFT = 0
	CHUNK_SIZE = 1024

	def __init__(self):
		self.sound_file = None
		self.buffer = None
		self.got_buffer = True
		self.path = None
		self.sound_info = None

	def buffer_loop(self):
		while True:
			while self.sound_file:
				self.set_buffer()
			time.sleep(.03)

	def load(self, path):
		self.path = path
		self.sound_file = soundfile.SoundFile(path)
		self.sound_info = soundfile.info(path)

	def set_buffer(self):
		data = self.sound_file.read(self.CHUNK_SIZE)
		# self.buffer = self.run_data_through_processes(data, self.get_processes())
		self.buffer = data
		self.got_buffer = False

	def get_buffer(self, outdata, frames, time, status):
		self.got_buffer = True
		print(self.buffer)
		outdata[:] = self.buffer

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

	@staticmethod
	def sum_to_mono(data):
		sound_data = np.average(data, axis=1)
		return sound_data

	def get_individual_channel(self, data):
		return self.get_individual_channels(data)[self.PLAY_INDIVIDUAL_CHANNEL]

	@staticmethod
	def get_individual_channels(data):
		sound_data = np.hsplit(data, data.shape[1])
		return sound_data


class AudioThread:
	def __init__(self):
		self.stream = None
		self.should_start = False
		self.should_stop = False

	def load(self, sample_rate, block, callback):
		self.reset()
		self.stream = sd.OutputStream(samplerate=sample_rate, blocksize=block, callback=callback)

	def reset(self):
		try:
			self.stream.close()
		except AttributeError:
			pass

	def play(self):
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
p.load(normal)
p.play()

while True:
	time.sleep(1)
