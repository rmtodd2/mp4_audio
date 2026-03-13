# MP4 Audio Tool

`mp4_audio.py` is a small Tkinter desktop app for adjusting audio in media files with FFmpeg.
It can change audio gain, mute audio, apply normalization, trim the media, and then save either:

- a new video file with the original video stream copied
- an audio-only export

## Requirements

This project does not require any pip-installable Python packages.
It uses only Python standard-library modules.

You do need:

- Python 3
- `ffmpeg` installed separately and available on your system `PATH`

## Run

```powershell
python mp4_audio.py
```
