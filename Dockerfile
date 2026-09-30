FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends git ffmpeg espeak-ng libportaudio2 \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml requirements-dev.lock ./
COPY src ./src
RUN python -m pip install --no-cache-dir -e '.[voice]'
COPY scripts ./scripts
COPY remote_eval ./remote_eval
COPY docs ./docs
RUN mkdir -p vendor && python scripts/setup_fdb.py
CMD ["python", "-m", "reactor.voice.agent", "start"]
