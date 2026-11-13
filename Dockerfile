# AITuber Libre — imagen única: FFmpeg propio + espeak-ng + FastAPI + React compilado
#
# FFmpeg se compila desde la fuente (9.0.2, última rama estable) en lugar de
# instalarse desde Alpine. El paquete de Alpine arrastra libass -> harfbuzz ->
# glib, y el escáner de la imagen marca glib con un rango invertido
# (ALPINE-CVE-2021-27219: "introducido en 2.67.0", "corregido en 2.66.6-r0"),
# es decir, sin versión corregida posible en ninguna rama de Alpine. Este
# renderizador no usa libass: los subtítulos se queman con drawtext (freetype),
# así que compilamos sin libass y glib no llega a la imagen final.

FROM node:24-alpine AS web

WORKDIR /web
COPY web/package.json /web/package.json
RUN npm install --no-audit --no-fund
COPY web/ /web/
RUN npm run build

FROM alpine:3.24 AS ffmpeg-build

RUN echo "os-refresh 2026-11-13" \
 && apk upgrade --no-cache \
 && apk add --no-cache build-base nasm pkgconf zlib-dev freetype-dev x264-dev

WORKDIR /src
ADD https://ffmpeg.org/releases/ffmpeg-9.0.2.tar.xz /src/ffmpeg.tar.xz
RUN tar -xf ffmpeg.tar.xz --strip-components=1 \
 && ./configure \
      --prefix=/usr/local \
      --disable-autodetect \
      --disable-doc \
      --disable-debug \
      --disable-ffplay \
      --disable-avdevice \
      --enable-gpl \
      --enable-libx264 \
      --enable-libfreetype \
      --enable-zlib \
 && make -j"$(nproc)" \
 && make install

FROM python:3.13-alpine

RUN echo "os-refresh 2026-11-13" \
 && apk upgrade --no-cache \
 && apk add --no-cache espeak-ng tzdata x264-libs freetype zlib \
 && (apk add --no-cache font-dejavu || apk add --no-cache ttf-dejavu)

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    AITUBER_DATA_DIR=/app/data \
    PORT=8080

COPY --from=ffmpeg-build /usr/local/bin/ffmpeg /usr/local/bin/ffmpeg
COPY --from=ffmpeg-build /usr/local/bin/ffprobe /usr/local/bin/ffprobe

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
