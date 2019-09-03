import soundfile
import sounddevice as sd
import threading
import multiprocessing
from ctypes import c_char_p
import time
import datetime
import numpy as np

# TODO Add pitch and time shifting
# TODO Add custom dithering

# wav_path = "Z:\\SFX Library\\SoundDogs\\" \
# 			"Humvee, Onb,55 MPH,Start Idle Revs,Drive Fast,Uphill Accelerate H,6003_966817.wav"
# normal = "Z:\\SFX Library\\SoundDogs\\M4 Grenade Launcher,Shots,Single x3 Double
# x1 Burst x20,C-Hard Mi,7242_966594.wav"
wav_96k = "C:\\Users\\smith\\Downloads\\Sounddogs_Order\\" \
			"Humvee, Onb,55 MPH,Start Idle Revs,Drive Fast,Uphill Accelerate H,6003_966817.wav"
# mp3_path = "Z:\\SFX Library\\ProSound\\2013 Flying Proms Junkers Ju 52 flight.mp3"
# count_path = "Z:\\SFX Library\\Digital Juice\\Digital Juice Files\\SFX_V01D07D\\Human\\OnTheSet\\" \
# 				"Check One, Two, Three Testing.Wav"
# ogg_path = "Z:\\SFX Library\\Digital Juice\\Digital Juice Files\\SFX_V03D01D_V2\\General\\Transportation\\" \
# 			"Train By 2.Ogg"
# flac_path = "C:\\Users\\Josh\\Downloads\\455746__kyles__door-apartment-buzzer-unlock-ext.flac"


def loop(connection):
	player = Player()
	while True:
		try:
			msg = connection.recv()
		except EOFError:
			pass
		else:
			if msg[0] == 'load':
				print('load')
				player.load(msg[1])
			elif msg[0] == 'play':
				print('play')
				player.play()
			elif msg[0] == 'pause':
				print('pause')
				player.pause()
			elif msg[0] == 'end':
				print('end')
				player.end()
			elif msg[0] == 'goto':
				print('goto')
				player.goto(msg[1])
			elif msg[0] == 'stop':
				print('stop')
				player.stop()
			elif msg[0] == 'set_volume':
				player.volume = msg[1]
			elif msg[0] == 'set_channels':
				player.audio_buffer.PLAY_INDIVIDUAL_CHANNELS = msg[1]
			elif msg == 'is_playing':
				connection.send(player.audio_playing)
			else:
				pass
		time.sleep(.02)


class PlayerProcess:
	def __init__(self):
		self.player = Player()
		self.parent_conn, self.child_conn = multiprocessing.Pipe()
		self.process = multiprocessing.Process(target=loop, args=(self.child_conn,))
		self.process.start()

	def play(self):
		self.parent_conn.send(('play',))

	def get_playing(self):
		self.parent_conn.send('is_playing')
		msg = self.parent_conn.recv()
		return msg

	def pause(self):
		self.parent_conn.send(('pause',))

	def load(self, path):
		self.parent_conn.send(('load', path))

	def goto(self, goto):
		self.parent_conn.send(('goto', goto))

	def stop(self):
		self.parent_conn.send(('stop',))

	def set_volume(self, volume_percentage: int):
		self.parent_conn.send(('set_volume', volume_percentage))

	def set_channels(self, channels: list):
		self.parent_conn.send(('set_channels', channels))


class Player:
	def __init__(self):
		self.audio_buffer = AudioBuffer(self.end)
		self.audio_buffer_thread = threading.Thread(target=self.audio_buffer.buffer_loop)
		self.audio_buffer_thread.start()
		self.audio_player = AudioThread(self.audio_buffer.ready)
		self.audio_player_thread = None
		self.playing = False
		self.paused = False
		self.ended = False
		self.started = False
		self._volume = 100

	@property
	def volume(self):
		return self._volume

	@volume.setter
	def volume(self, value: int):
		if value <= 200:
			try:
				self.audio_buffer.VOLUME_PERCENTAGE = value
			except AttributeError:
				pass
			self._volume = value

	def load(self, path):
		self.audio_buffer.load(path)
		self.audio_buffer.processes = self.audio_buffer.get_processes()
		# self.audio_buffer.CHUNK_SIZE = self.audio_buffer.get_recommended_chunk_size()
		self.audio_buffer.chunk_set = True
		self.audio_player.load(self.audio_buffer.sound_info.samplerate, self.audio_buffer.CHUNK_SIZE,
								self.audio_buffer.channels, self.audio_buffer.get_buffer)

	@property
	def audio_playing(self):
		return self.audio_player.active

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

	def start_audio_thread(self):
		self.audio_player_thread = threading.Thread(target=self.audio_player.run_loop)
		self.audio_player_thread.start()

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
		self.start_audio_thread()
		self.playing = True
		self.paused = False

	def pause(self):
		self.audio_player.pause()
		self.paused = True

	def stop(self):
		self.audio_buffer.stop()
		self.audio_player.stop()
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
	VOLUME_PERCENTAGE = 100

	def __init__(self, end_callback):
		self.end_callback = end_callback
		self.sound_file = None
		self.buffer = []
		self.path = None
		self.sound_info = None
		self.finished = False
		self.loaded = False
		self.chunk_set = False
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
			while self.sound_file and len(self.buffer) < 50 and not self.finished:
				self.set_buffer()
				self.loaded = True
			time.sleep(.03)

	def load(self, path):
		self.finished = False
		self.path = path
		self.sound_file = soundfile.SoundFile(path)
		self.sound_info = soundfile.info(path)

	def set_buffer(self):
		data = self.get_correct_amount_of_channels(self.get_selected_channels(self.sound_file.read(self.CHUNK_SIZE)))
		padded_data = self.pad_sound(data)
		data_with_effects = self.run_data_through_processes(padded_data, self.processes)
		data_at_correct_volume = self.set_volume(data_with_effects)
		self.buffer.append(data_at_correct_volume)

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

	def stop(self):
		self.sound_file = None
		self.chunk_set = False
		self.buffer = []

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

	def set_volume(self, data):
		if self.VOLUME_PERCENTAGE != 100:
			percent = self.VOLUME_PERCENTAGE/100
			return data * percent
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

	@property
	def active(self):
		try:
			return self.stream.active
		except AttributeError:
			return False

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

	def stop(self):
		self.pause()
		self.stream = None

	def run_loop(self):
		while True:
			if self.should_start and self.ready_callback():
				self.stream.start()
				self.should_start = False
				break
			time.sleep(.03)


if __name__ == "__main__":
	p = Player()
	p.load(wav_96k)
	p.audio_buffer.VOLUME_PERCENTAGE = 100
	# while not p.audio_buffer.loaded:
	# 	time.sleep(.001)
	p.play()
	# time.sleep(5)
	# p.goto(10000)

	while True:
		time.sleep(1)
