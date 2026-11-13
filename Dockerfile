# AITuber Libre — imagen única: FFmpeg + espeak-ng + FastAPI + React compilado
FROM node:24-alpine AS web

WORKDIR /web
COPY web/package.json /web/package.json
RUN npm install --no-audit --no-fund
COPY web/ /web/
RUN npm run build

FROM python:3.13-alpine3.22

RUN echo "os-refresh 2026-11-13" \
 && apk upgrade --no-cache \
 && apk add --no-cache ffmpeg espeak-ng tzdata \
 && (apk add --no-cache font-dejavu || apk add --no-cache ttf-dejavu)

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    AITUBER_DATA_DIR=/app/data \
    PORT=8080

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY app/ /app/app/
COPY --from=web /web/dist /app/web/dist

# El proceso corre sin privilegios y solo es dueño de sus propios directorios.
RUN addgroup -S aituber \
 && adduser -S -G aituber -h /app aituber \
 && mkdir -p /app/data/music /app/data/renders /app/data/exports /app/data/media /app/data/tmp \
 && chown -R aituber:aituber /app

USER aituber

EXPOSE 8080
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
