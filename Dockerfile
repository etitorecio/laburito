# Laburito — FastAPI + React + FFmpeg del sistema.
# Debian/glibc permite instalar Piper/ONNX Runtime con ruedas manylinux oficiales.

FROM node:24-alpine AS web
WORKDIR /web
COPY web/package.json /web/package.json
COPY web/package-lock.json /web/package-lock.json
RUN npm ci --no-audit --no-fund
COPY web/ /web/
RUN npm run build

FROM python:3.13-slim-bookworm
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ffmpeg espeak-ng tzdata ca-certificates fonts-dejavu-core \
      libstdc++6 libgomp1 \
 && rm -rf /var/lib/apt/lists/* \
 && ffmpeg -hide_banner -filters 2>/dev/null | grep -q drawtext \
 && ffmpeg -hide_banner -encoders 2>/dev/null | grep -q libx264

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    AITUBER_DATA_DIR=/app/data \
    PORT=8080

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r /app/requirements.txt

COPY app/ /app/app/
COPY --from=web /web/dist /app/web/dist

RUN groupadd --system aituber \
 && useradd --system --gid aituber --home-dir /app aituber \
 && mkdir -p /app/data/music /app/data/renders /app/data/exports /app/data/media /app/data/tmp \
 && chown -R aituber:aituber /app

USER aituber
EXPOSE 8080
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
