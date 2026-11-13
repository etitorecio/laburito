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
 && apk add --no-cache build-base nasm pkgconf zlib-dev freetype-dev x264-dev meson ninja

# Harfbuzz sin glib: FFmpeg 8/9 exigen libharfbuzz para el filtro drawtext
# (subtitulos quemados), pero el paquete de Alpine lo enlaza con glib, que el
# escaner marca con un rango invertido (ALPINE-CVE-2021-27219) sin correccion
# posible en ninguna rama. Se compila aqui con glib desactivado y a la imagen
# final solo se copia la libreria resultante.
WORKDIR /hb
ADD https://github.com/harfbuzz/harfbuzz/releases/download/15.1.0/harfbuzz-15.1.0.tar.xz /hb/hb.tar.xz
RUN tar -xf hb.tar.xz \
 && meson setup build harfbuzz-15.1.0 \
      --prefix=/usr/local --buildtype=release \
      -Dglib=disabled -Dgobject=disabled -Dicu=disabled -Dcairo=disabled \
      -Ddocs=disabled -Dtests=disabled -Dintrospection=disabled \
      -Dfreetype=enabled \
 && ninja -C build install

WORKDIR /src
ADD https://ffmpeg.org/releases/ffmpeg-9.0.2.tar.xz /src/ffmpeg.tar.xz
RUN tar -xf ffmpeg.tar.xz --strip-components=1 \
 && ./configure \
      --prefix=/usr/local \
      --disable-autodetect \
      --disable-doc \
      --disable-debug \
      --disable-ffplay \
      --enable-gpl \
      --enable-libx264 \
      --enable-libfreetype \
      --enable-libharfbuzz \
      --enable-zlib \
 && make -j"$(nproc)" \
 && make install

FROM python:3.13-alpine

RUN echo "os-refresh 2026-11-13" \
 && apk upgrade --no-cache \
 && apk add --no-cache espeak-ng tzdata x264-libs freetype zlib libstdc++ \
 && (apk add --no-cache font-dejavu || apk add --no-cache ttf-dejavu)

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    AITUBER_DATA_DIR=/app/data \
    LD_LIBRARY_PATH=/usr/local/lib \
    PORT=8080

COPY --from=ffmpeg-build /usr/local/bin/ffmpeg /usr/local/bin/ffmpeg
COPY --from=ffmpeg-build /usr/local/bin/ffprobe /usr/local/bin/ffprobe
COPY --from=ffmpeg-build /usr/local/lib/libharfbuzz.so* /usr/local/lib/

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
