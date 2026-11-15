# Laburito — FFmpeg compilado sin libass/GLib + FastAPI + React.
# Debian/glibc es necesario para las ruedas oficiales manylinux de ONNX Runtime
# usadas por Piper TTS; Alpine/musl no tiene esas ruedas y rompería el contenedor.

FROM node:24-alpine AS web
WORKDIR /web
COPY web/package.json /web/package.json
COPY web/package-lock.json /web/package-lock.json
RUN npm ci --no-audit --no-fund
COPY web/ /web/
RUN npm run build

FROM debian:bookworm-slim AS ffmpeg-build
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      build-essential nasm pkg-config zlib1g-dev libfreetype6-dev libx264-dev \
      meson ninja-build ca-certificates xz-utils python3 \
 && rm -rf /var/lib/apt/lists/*

# HarfBuzz se compila sin GLib para mantener la dependencia mínima.
WORKDIR /hb
ADD https://github.com/harfbuzz/harfbuzz/releases/download/15.1.0/harfbuzz-15.1.0.tar.xz /hb/hb.tar.xz
RUN tar -xf hb.tar.xz \
 && meson setup build harfbuzz-15.1.0 \
      --prefix=/usr/local --libdir=lib --buildtype=release \
      -Dglib=disabled -Dgobject=disabled -Dicu=disabled -Dcairo=disabled \
      -Ddocs=disabled -Dtests=disabled -Dintrospection=disabled \
      -Dfreetype=enabled \
 && ninja -C build install

WORKDIR /src
ADD https://ffmpeg.org/releases/ffmpeg-9.0.2.tar.xz /src/ffmpeg.tar.xz
RUN export PKG_CONFIG_PATH=/usr/local/lib/pkgconfig:$PKG_CONFIG_PATH \
 && tar -xf ffmpeg.tar.xz --strip-components=1 \
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

FROM python:3.13-slim-bookworm
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      espeak-ng tzdata ca-certificates libx264-164 libfreetype6 zlib1g \
      libstdc++6 libgomp1 fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

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
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r /app/requirements.txt \
 && ! ldd /usr/local/bin/ffmpeg | grep -q "not found"

COPY app/ /app/app/
COPY --from=web /web/dist /app/web/dist

RUN addgroup --system aituber \
 && adduser --system --ingroup aituber --home /app aituber \
 && mkdir -p /app/data/music /app/data/renders /app/data/exports /app/data/media /app/data/tmp \
 && chown -R aituber:aituber /app

USER aituber
EXPOSE 8080
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
