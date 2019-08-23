import soundfile
import sounddevice as sd
import time
import numpy as np

wav_path = "Z:\\SFX Library\\SoundDogs\\Humvee, Onb,55 MPH,Start Idle Revs,Drive Fast,Uphill Accelerate H,6003_966817" \
			".wav"
normal = "Z:\\SFX Library\\Digital Juice\\Digital Juice Files\\SFX_V04D05D\\Human\\" \
			"AmericanPoliticsMale\\As Maine Goes So Goes The Nation Male English 2.Wav"
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

class AudioBuffer:
	SUM_TO_MONO = True
	PLAY_INDIVIDUAL_CHANNEL = 0
	PITCH_SHIFT = 0
	TIME_SHIFT = 0
	CHUNK_SIZE = 1024

	def __init__(self):
		self.sound_file = None
		self.buffer = None

	def load(self, path):
		self.sound_file = soundfile.SoundFile(path)

	def set_buffer(self):
		print(self.sound_file.buffer_read(self.CHUNK_SIZE))

	def get_processes(self):
		processes = []
		if self.PLAY_INDIVIDUAL_CHANNEL > 0:
			processes.append(self.get_individual_channel)
		if self.SUM_TO_MONO:
			processes.append(self.sum_to_mono)

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


s = AudioBuffer()
s.load(wav_path)
s.set_buffer()

while True:
	time.sleep(1)
