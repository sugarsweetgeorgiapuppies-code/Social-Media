# SSGP Editor — runs identically on any computer or server.
# Bundles FFmpeg + fonts + Python deps so there's nothing to install by hand.
FROM python:3.12-slim

# FFmpeg for all video/audio work (fonts are bundled in ./fonts, drawn by Pillow)
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# install deps first (better layer caching)
COPY requirements.txt .
RUN pip install -r requirements.txt

# app code
COPY . .

EXPOSE 8080

# faster-whisper caches its model here; mount a volume to persist it. On hosts
# that inject $PORT (Render/Railway/Fly), run.py binds that automatically.
ENV HF_HOME=/root/.cache/huggingface

CMD ["python", "run.py", "--host", "0.0.0.0"]
