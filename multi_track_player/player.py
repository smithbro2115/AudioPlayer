import soundfile
import sounddevice as sd
import threading
import multiprocessing
from ctypes import c_char_p
import time
import datetime
import numpy as np
import math
import requests
import miniaudio
from multi_track_player import Exceptions
from pathlib import Path

# TODO Add pitch and time shifting
# TODO Add custom dithering

# wav_path = "Z:\\SFX Library\\SoundDogs\\" \
# 			"Humvee, Onb,55 MPH,Start Idle Revs,Drive Fast,Uphill Accelerate H,6003_966817.wav"
# normal = "Z:\\SFX Library\\SoundDogs\\M4 Grenade Launcher,Shots,Single x3 Double
# x1 Burst x20,C-Hard Mi,7242_966594.wav"
wav_96k = "Z:/SFX Library/Organized SFX Library\\Vehicles, Machinery\\Cars\\2001 100s Land Cruiser\\Land Cruiser 100 Car Door Open Close Exterior 1.Wav"
wav_48k = "C:\\Users\\smith\\Downloads\\404687__straget__hooded-crow.wav"
URL = "https://freesound.org/data/previews/328/328165_5121236-lq.mp3"
URL_2 = "https://www.sounddogs.com/media/fastpreview/Sounddogs-Preview-10946164.mp3"
URL_3 = "https://freesound.org/data/previews/509/509363_1648170-lq.mp3"
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
				player.load(msg[1], duration=msg[2])
			elif msg == 'reload':
				player.reload()
			elif msg[0] == 'play':
				player.play()
			elif msg[0] == 'pause':
				player.pause()
			elif msg[0] == 'end':
				player.end()
			elif msg[0] == 'goto':
				player.goto(msg[1])
			elif msg[0] == 'stop':
				try:
					player.stop()
				except AttributeError:
					pass
			elif msg[0] == 'set_volume':
				player.volume = msg[1]
			elif msg[0] == 'set_channels':
				player.audio_buffer.PLAY_INDIVIDUAL_CHANNELS = msg[1]
			elif msg == 'is_playing':
				connection.send(player.audio_playing)
			elif msg == "start_time":
				connection.send(player.start_time)
			elif msg == "state":
				connection.send(player.state)
			elif msg == "latency":
				connection.send(player.latency)
			elif msg == "current_time":
				try:
					connection.send(player.audio_buffer.current_time_calculated)
				except AttributeError:
					connection.send(0)
			elif msg == "close_process":
				break
			else:
				pass
		time.sleep(.02)


class PlayerProcess:
	def __init__(self):
		self.parent_conn, self.child_conn = multiprocessing.Pipe()
		self.process = multiprocessing.Process(target=loop, args=(self.child_conn,))
		self.process.start()

	def __del__(self):
		self.parent_conn.send("close_process")

	@property
	def state(self):
		self.parent_conn.send("state")
		msg = self.parent_conn.recv()
		return msg

	@property
	def latency(self):
		self.parent_conn.send("latency")
		msg = self.parent_conn.recv()
		return msg

	@property
	def current_time(self):
		self.parent_conn.send("current_time")
		msg = self.parent_conn.recv()
		return msg

	def get_start_time(self):
		self.parent_conn.send("start_time")
		msg = self.parent_conn.recv()
		return msg

	def play(self):
		self.parent_conn.send(('play',))

	def get_playing(self):
		self.parent_conn.send('is_playing')
		msg = self.parent_conn.recv()
		return msg

	def pause(self):
		self.parent_conn.send(('pause',))

	def load(self, path, duration=None):
		self.parent_conn.send(('load', path, duration))

	def reload(self):
		self.parent_conn.send("reload")

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
		self.audio_player = AudioThread(self._ready)
		self.audio_player_thread = None
		self.state = 'idle'
		self.start_time = None
		self.pause_time = None
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

	@property
	def latency(self):
		try:
			return self.audio_player.stream.latency
		except AttributeError:
			return 0

	def _ready(self):
		try:
			return self.audio_buffer.ready()
		except AttributeError:
			return False

	def setup_audio_buffer(self, type, *args):
		self.audio_buffer = type(*args)
		self.audio_buffer_thread = threading.Thread(target=self.audio_buffer.buffer_loop, daemon=True)
		self.audio_buffer_thread.start()

	def load(self, path, duration=None):
		self.state = "loading"
		self._load_correct_buffer(path, duration)
		self.audio_buffer.processes = self.audio_buffer.get_processes()
		# self.audio_buffer.CHUNK_SIZE = self.audio_buffer.get_recommended_chunk_size()
		self.audio_buffer.chunk_set = True
		self.audio_player.load(self.audio_buffer.sound_info['sample_rate'], self.audio_buffer.sound_info['dtype'],
							   self.audio_buffer.CHUNK_SIZE, self.audio_buffer.channels, self.audio_buffer.get_buffer)
		self.state = "idle"

	def _load_correct_buffer(self, path, duration=None):
		local_path = Path(path)
		if path.startswith("http"):
			self._load_remote(path, duration)
		elif local_path.suffix.lower() == ".mp3":
			self._load_mp3(local_path)
		else:
			self._load_local(local_path)

	def _load_remote(self, url, duration):
		self.setup_audio_buffer(RemoteAudioBuffer, self.end)
		self.audio_buffer.load(url, duration)

	def _load_local(self, path):
		self.setup_audio_buffer(AudioBuffer, self.end)
		self.audio_buffer.load(path)

	def _load_mp3(self, path):
		self.setup_audio_buffer(Mp3Buffer, self.end)
		self.audio_buffer.load(path)

	def reload(self):
		self.state = "loading"
		self.audio_buffer.reload()
		self.audio_buffer.processes = self.audio_buffer.get_processes()
		self.audio_buffer.chunk_set = True
		self.audio_player.load(self.audio_buffer.sound_info['sample_rate'], self.audio_buffer.sound_info['dtype'],
							   self.audio_buffer.CHUNK_SIZE, self.audio_buffer.channels, self.audio_buffer.get_buffer)
		self.state = "idle"

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
		self.audio_player_thread = threading.Thread(target=self.audio_player.run_loop, daemon=True)
		self.audio_player_thread.start()

	def determine_summing_policy(self):
		if self.audio_buffer.sound_info.channels > 2:
			self.audio_buffer.SUM_TO_MONO = True
		else:
			self.audio_buffer.SUM_TO_MONO = False

	def end(self):
		self.state = 'idle'
		raise sd.CallbackStop

	def play(self):
		self.audio_player.play()
		self.start_audio_thread()
		self.state = "playing"
		self.start_time = datetime.datetime.now() + datetime.timedelta(seconds=self.latency)

	def pause(self):
		self.audio_player.pause()
		self.state = 'paused'

	def stop(self):
		self.audio_player.stop()
		self.audio_buffer.stop()
		self.state = 'stopped'

	def goto(self, goto):
		paused = False
		if self.state == "paused":
			paused = True
		self.stop()
		self.audio_buffer.seek(goto, self.reload)
		if not paused:
			self.play()
		else:
			self.pause()


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
		self._buffer = []
		self.path = None
		self.sound_info = None
		self.state = 'idle'
		self.finished = False
		self.loaded = False
		self.chunk_set = False
		self.current_frame = 0
		self._chunk_sizes = []
		self.processes = []

	@property
	def buffer(self):
		return self._buffer

	@buffer.setter
	def buffer(self, value):
		self._buffer = value

	@property
	def _loaded(self):
		if self.sound_file:
			return True
	@property
	def _should_end(self):
		return self.finished and len(self.buffer) == 0

	@property
	def channels(self):
		if self.SUM_TO_MONO or self.sound_info['nchannels'] == 1:
			return 1
		return 2

	@property
	def current_time(self):
		try:
			return int((self.current_frame/self.sound_info['sample_rate'])*1000)
		except KeyError:
			return 0

	@current_time.setter
	def current_time(self, value):
		try:
			self.current_frame = int((value/1000)*self.sound_info['sample_rate'])
		except KeyError:
			self.current_frame = 0

	def ready(self):
		return len(self.buffer) > 0

	def buffer_loop(self):
		while True:
			while self._loaded and len(self.buffer) < 50 and not self.finished and self.state == "idle":
				self.set_buffer(self._read())
				self.loaded = True
			time.sleep(.03)

	def load(self, path, *args):
		self.state = "loading"
		self.finished = False
		self.path = path
		self._load(path, *args)
		self.state = 'idle'

	def _load(self, path):
		self.sound_file = soundfile.SoundFile(path)
		info = soundfile.info(path)
		self.sound_info = {"sample_rate": info.samplerate, "nchannels": info.channels, "frames": info.frames,
						   "duration": info.duration, 'dtype': 'float32'}
	def reload(self):
		self._load(self.path)

	def set_buffer(self, raw_data):
		data = self.get_correct_amount_of_channels(self.get_selected_channels(raw_data))
		padded_data = self.pad_sound(data)
		data_with_effects = self.run_data_through_processes(padded_data, self.processes)
		data_at_correct_volume = self.set_volume(data_with_effects)
		self.buffer.append(data_at_correct_volume)

	def _read(self):
		return self.sound_file.read(self.CHUNK_SIZE, dtype='float32')

	def seek(self, goto, reload_callback):
		"""
		Set read from frame
		:param goto:
			should be in milliseconds
		:param reload_callback:
			to reload parent
		"""
		self.state = "seeking"
		self.current_time = goto
		self._seek(goto, reload_callback)
		self.state = 'idle'

	def _seek(self, goto, reload_callback):
		self.buffer = []
		reload_callback()
		goto_frame = int(self.sound_info['sample_rate'] * (goto / 1000))
		try:
			self.sound_file.seek(goto_frame)
		except RuntimeError:
			self.sound_file.seek(self.sound_info['frames']-1)

	def stop(self):
		self.sound_file = None
		self.chunk_set = False
		self.current_frame = 0
		self.finished = False
		self.loaded = False
		self.chunk_set = False
		self.buffer = []
		self._chunk_sizes = []

	def pad_sound(self, data):
		data_chunk_size = data.shape[0]
		if 0 < data_chunk_size < self.CHUNK_SIZE:
			data = np.pad(data, [(0, self.CHUNK_SIZE - data_chunk_size), (0, 0)], mode='constant')
			self.finished = True
		return data

	def get_recommended_chunk_size(self):
		"""Make sure to set processes first"""
		chunk_size = 1024
		if self.sound_info['nchannels'] > 2:
			chunk_size += 1024 * (self.sound_info['nchannels'] - 2)
		if len(self.PLAY_INDIVIDUAL_CHANNELS) > 0:
			chunk_size += 1024
		return chunk_size

	def get_buffer(self, outdata, frames, time, status):
		outdata[:] = self.buffer.pop(0)
		self.current_frame += self.CHUNK_SIZE
		self.current_time_calculated = int((self.current_frame/self.sound_info['sample_rate'])*1000)
		if self._should_end:
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
			new_data = np.ndarray(buffer=data, shape=(data.shape[0], 1), dtype=self.sound_info['dtype'])
			return new_data
		return data

	def set_volume(self, data):
		if self.VOLUME_PERCENTAGE != 100:
			percent = self.VOLUME_PERCENTAGE/100
			return data * percent
		return data

	def sum_to_mono(self, data):
		sound_data = np.ndarray(buffer=np.average(data, axis=1), shape=(data.shape[0], 1),
								dtype=self.sound_info['dtype'])
		return sound_data

	def get_selected_channels(self, data):
		if len(self.PLAY_INDIVIDUAL_CHANNELS) > 0:
			return self._get_selected_channels_from_play_channels(data)
		return data

	def _get_selected_channels_from_play_channels(self, data):
		channels = self.get_individual_channels(data)
		selected_channels = np.ndarray((data.shape[0], 0), dtype=self.sound_info['dtype'])
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


class Mp3Buffer(AudioBuffer):
	def __del__(self):
		try:
			self.sound_file.close()
		except AttributeError:
			pass

	def _load(self, path):
		info = miniaudio.mp3_get_file_info(path)
		self.sound_info = {"sample_rate": info.sample_rate, "nchannels": info.nchannels, "frames": info.num_frames,
						   "duration": info.duration, 'dtype': 'int16'}
		self.sound_file = miniaudio.stream_file(path,
												sample_rate=self.sound_info['sample_rate'],
												nchannels=self.sound_info['nchannels'],
												frames_to_read=self.CHUNK_SIZE
												)

	def _read(self):
		return self._decode(self.sound_file.__next__())

	def _decode(self, data):
		audio_array = np.array(data)
		return audio_array.reshape((math.ceil(len(audio_array) / self.sound_info['nchannels']),
									self.sound_info['nchannels']))

	def _seek(self, goto, reload_callback):
		self.buffer = []
		reload_callback()
		goto_frame = int(self.sound_info['sample_rate'] * (goto / 1000))
		try:
			self.sound_file = miniaudio.stream_file(self.path,
													sample_rate=self.sound_info['sample_rate'],
													nchannels=self.sound_info['nchannels'],
													frames_to_read=self.CHUNK_SIZE,
													seek_frame=goto_frame
													)
		except RuntimeError:
			self.sound_file = miniaudio.stream_file(self.path,
													sample_rate=self.sound_info['sample_rate'],
													nchannels=self.sound_info['nchannels'],
													frames_to_read=self.CHUNK_SIZE,
													seek_frame=self.sound_info["frames"]-1
													)


class RequestBuffer(threading.Thread):
	REQUEST_BUFFER_SIZE = 2500000 * 3
	REQUEST_CHUNK_SIZE = 1024 * 100

	def __init__(self, parent, *args, **kwargs):
		super(RequestBuffer, self).__init__(*args, **kwargs)
		self.buffer = None
		self.requested_all = False
		self.decoded_all = False
		self.request = None
		self.request_headers = None
		self.canceled = False
		self.sound_info = None
		self.parent = parent

	@property
	def request_buffer_is_full(self):
		try:
			return self.buffer.shape[0] >= self.REQUEST_BUFFER_SIZE
		except AttributeError:
			return False

	@property
	def finished(self):
		return self.requested_all and self.buffer.shape[0] == 0

	@property
	def bitrate(self):
		try:
			return int(self.request_headers['Content-Length']) / self.sound_info['duration']
		except TypeError:
			return None

	def load(self, url, duration):
		self.reset()
		request = requests.get(url, stream=True)
		self.request = request.iter_content(self.REQUEST_CHUNK_SIZE)
		self.request_headers = request.headers
		file_type = self.request_headers['Content-Type']
		first_chunk = self.request.__next__()
		info = self.get_info_from_file_type(first_chunk, file_type)
		self.sound_info = {"sample_rate": info.sample_rate, "nchannels": info.nchannels, 'duration': duration,
						   'dtype': info.sample_format, 'file_type': file_type, 'url': url}
		self.append_to_request_buffer(self._decode_request(first_chunk))
		return self.sound_info

	def reload(self, request_headers, sound_info):
		self.reset()
		self.request_headers = request_headers
		self.sound_info = sound_info
		return self.sound_info

	def reset(self):
		self.buffer = None
		self.requested_all = False
		self.decoded_all = False
		self.canceled = False

	def seek(self, goto):
		"""

		:param goto: time in milliseconds
		:return:
		"""
		self.buffer = None
		goto_byte = int(self.calculate_byte_from_milliseconds(int(goto)))
		if goto_byte > int(self.request_headers['Content-Length']) or goto_byte < 0:
			raise Exceptions.TimeOutOfRange(f"{goto}ms is not within the time range of this sound")
		headers = {"Range": f"bytes={goto_byte}-"}
		self.request = requests.get(self.sound_info['url'],
									stream=True, headers=headers).iter_content(self.REQUEST_CHUNK_SIZE)
		self.append_to_request_buffer(self._read_request())

	def calculate_byte_from_milliseconds(self, milliseconds):
		return self.bitrate * milliseconds

	@staticmethod
	def get_info_from_file_type(data, file_type):
		if file_type in [".mp3", "audio/mpeg"]:
			return miniaudio.mp3_get_info(data)
		elif file_type in [".ogg", "audio/ogg"]:
			return miniaudio.vorbis_get_info(data)
		elif file_type in [".wav", "audio/wav", "audio/x-wav"]:
			return miniaudio.wav_get_info(data)
		elif file_type in [".flac", "audio/flac", "audio/x-flac"]:
			return miniaudio.flac_get_info(data)
		else:
			raise TypeError(f"{file_type} is an unsupported file type")

	def cancel(self):
		self.canceled = True

	def run(self) -> None:
		while not self.requested_all and not self.canceled:
			while self.parent._loaded and self.parent.state in ["idle", "loading"] and not self.request_buffer_is_full:
				try:
					self.append_to_request_buffer(self._read_request())
				except StopIteration:
					self.requested_all = True
					break
			time.sleep(.03)

	def append_to_request_buffer(self, data):
		try:
			self.buffer = np.concatenate((self.buffer, data))
		except ValueError:
			self.buffer = data
		if self.requested_all:
			self.decoded_all = True

	def _read_request(self):
		chunk = self.request.__next__()
		return self._decode_request(chunk)

	def _decode_request(self, request_data):
		decoder = miniaudio.decode(request_data, sample_rate=self.sound_info['sample_rate'],
								   nchannels=self.sound_info['nchannels'])
		samples = np.array(decoder.samples)
		decoded_chunk = samples.reshape((math.ceil(len(samples) / decoder.nchannels), decoder.nchannels))
		return decoded_chunk



class RemoteAudioBuffer(AudioBuffer):
	def __init__(self, end_callback):
		super(RemoteAudioBuffer, self).__init__(end_callback)
		self.request_buffer = None
		self.last_request_headers = None
		self.last_sound_info = None

	@property
	def _loaded(self):
		try:
			if self.request_buffer.request:
				return True
		except AttributeError:
			return False

	@property
	def _should_end(self):
		try:
			return self.finished and len(self.buffer) == 0 and self.request_buffer.finished
		except AttributeError:
			return self.finished and len(self.buffer) == 0

	def stop(self):
		self.last_request_headers = self.request_buffer.request_headers
		self.last_sound_info = self.request_buffer.sound_info
		self.request_buffer.cancel()
		self.request_buffer = None
		super(RemoteAudioBuffer, self).stop()

	def _load(self, path, duration):
		self.request_buffer = RequestBuffer(self, daemon=True)
		self.sound_info = self.request_buffer.load(path, duration)
		self.request_buffer.start()

	def reload(self):
		self.request_buffer = RequestBuffer(self, daemon=True)
		if not self.last_request_headers:
			self.sound_info = self.request_buffer.load(self.path, self.sound_info['duration'])
		else:
			self.sound_info = self.request_buffer.reload(self.last_request_headers, self.last_sound_info)

	def _read(self):
		chunk = self.request_buffer.buffer[:self.CHUNK_SIZE]
		self.request_buffer.buffer = np.delete(self.request_buffer.buffer, slice(self.CHUNK_SIZE), 0)
		return chunk

	def _seek(self, goto, reload_callback):
		"""

		:param goto: time in milliseconds
		:param reload_callback: this will get called before seeking
		:return:
		"""
		reload_callback()
		self.request_buffer.seek(goto)
		self.request_buffer.start()



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

	def load(self, sample_rate, dtype, block, channels, callback):
		self.reset()
		self.stream = sd.OutputStream(samplerate=sample_rate, blocksize=block, channels=channels, callback=callback,
									  dtype=self.get_dtype_string(dtype))

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

	@staticmethod
	def get_dtype_string(value):
		if type(value) == str:
			return value
		if value == miniaudio.SampleFormat.UNSIGNED8:
			return 'uint8'
		elif value == miniaudio.SampleFormat.SIGNED16:
			return 'int16'
		elif value == miniaudio.SampleFormat.SIGNED24:
			return 'int24'
		elif value == miniaudio.SampleFormat.SIGNED32:
			return 'int32'
		elif value == miniaudio.SampleFormat.FLOAT32:
			return 'float32'
		raise TypeError(f"The {value} dtype is not supported")

	def run_loop(self):
		while True:
			if self.should_start and self.ready_callback():
				self.stream.start()
				self.should_start = False
				break
			time.sleep(.03)


if __name__ == "__main__":
	p = Player()
	# p.load(URL_3)
	# # while not p.audio_buffer.loaded:
	# # 	time.sleep(.001)
	# p.play()
	# time.sleep(5)
	# p.stop()
	p.load(wav_96k)
	p.play()
	# time.sleep(5)
	# p.goto(21000)
	# time.sleep(.5)
	# p.goto(2000)
	# time.sleep(5)
	# p.goto(10000)

	while True:
		time.sleep(1)
