# Verified Runtime

CreativeOS V1 was verified with:

- Python 3.12.10
- Node.js 24.20.0
- npm 11.19.0
- FFmpeg 9.0.2
- FFprobe 9.0.2

`backend/requirements.txt` pins the complete tested Python dependency set for the backend. The media and QA tests require `ffmpeg` and `ffprobe` on `PATH`; they do not call live provider APIs.
