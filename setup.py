from setuptools import setup

with open('requirements.txt', 'r') as f:
    requirements = f.read()

setup(name='multi_track_player',
      version='0.1',
      description="Play multi-track WAV files, also plays FLACs, OGGs, and ALAC files",
      author="smithbro",
      author_email="smithbro2115@gmail.com",
      license='MIT',
      packages=['multi_track_player'],
      install_requires=[requirements],
      zip_safe=False)
