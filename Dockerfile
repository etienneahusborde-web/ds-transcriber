# Build du décodeur natif DS2
FROM rust:1-bookworm AS decoder
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 https://github.com/hirparak/dss-codec.git /src/dss-codec
WORKDIR /src/dss-codec/dss-codec
RUN cargo build --release

# Build natif de whisper.cpp
FROM debian:bookworm AS whisper
RUN apt-get update && apt-get install -y --no-install-recommends git cmake build-essential ca-certificates curl && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 https://github.com/ggml-org/whisper.cpp.git /src/whisper.cpp
WORKDIR /src/whisper.cpp
RUN cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DGGML_NATIVE=OFF -DWHISPER_BUILD_TESTS=OFF && cmake --build build --config Release -j 2
RUN mkdir -p /models && curl -fL --retry 3 -o /models/ggml-tiny.bin https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.bin

# Image d'exécution légère
FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libgomp1 libstdc++6 && rm -rf /var/lib/apt/lists/*
COPY --from=decoder /src/dss-codec/dss-codec/target/release/dss-decode /usr/local/bin/dss-decode
COPY --from=whisper /src/whisper.cpp/build/bin/ /usr/local/bin/
COPY --from=whisper /src/whisper.cpp/build/src/ /usr/local/lib/
COPY --from=whisper /src/whisper.cpp/build/ggml/src/ /usr/local/lib/
COPY --from=whisper /models/ggml-tiny.bin /opt/models/ggml-tiny.bin
ENV LD_LIBRARY_PATH=/usr/local/lib PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py ./
COPY templates/ ./templates/
COPY static/ ./static/
ENV PORT=10000
CMD ["sh", "-c", "exec gunicorn -w 1 --threads 4 --timeout 60 -b 0.0.0.0:${PORT} app:app"]
