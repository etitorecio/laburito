# AITuber Libre

Plataforma local para **investigar nichos, gestionar canales y producir documentales y Shorts** listos para revisar y publicar. Todo funciona con software libre, sin APIs de pago y sin claves: la app renderiza vídeo real con FFmpeg y voz con espeak-ng.

> Estado honesto: el guion, la voz, los subtítulos, el render, la cola y la exportación son reales y se prueban de punta a punta. La búsqueda de material externo consulta repositorios libres (Wikimedia Commons, Openverse, Internet Archive) cuando hay red; si no hay red o no hay resultados, cada escena usa una tarjeta visual generada localmente y el informe de calidad lo advierte. La publicación automática en YouTube/TikTok **no** está implementada (requiere credenciales OAuth del usuario): la app entrega el paquete listo para subir.

## Qué hace

- **Investigación**: nichos con demanda, competencia, riesgo de copyright y potencial de serie; notas con nivel de evidencia, fuente y fecha de consulta; búsqueda de imágenes con licencia.
- **Canales**: identidad, tono, idioma, formatos y cadencia.
- **Guion**: estructura narrativa de documental (8–20 min) o Short, editable escena por escena, regenerable, con búsqueda visual y transición por escena.
- **Voz**: espeak-ng local (voz española, velocidad y tono ajustables). Piper es opcional mediante `PIPER_BIN` + `PIPER_MODEL`.
- **Render**: FFmpeg horizontal 16:9, vertical 9:16 o cuadrado 1:1, con subtítulos quemados, miniaturas y música de fondo opcional.
- **Cola persistente**: un trabajo a la vez, reanudable tras reinicio y con caché por escena (no repite trabajo).
- **Entrega**: ZIP con MP4, SRT, VTT, guion en Markdown, fuentes/atribuciones en CSV, miniaturas, metadatos de publicación e informe de calidad.
- **Analítica**: importación del CSV real de YouTube Studio (no inventa métricas) y resumen con hipótesis.
- **Calendario**: programación editorial por canal.
- **Biblioteca**: todo lo producido o descargado, con licencia y autor.
- **Diagnóstico**: estado real de FFmpeg, fuentes, voz, base de datos, espacio y worker.

## Instalación local

Requisitos: Python 3.11+, FFmpeg y espeak-ng.

```bash
# Debian/Ubuntu
sudo apt install ffmpeg espeak-ng fonts-dejavu-core

pip install -r requirements.txt
cd web && npm install && npm run build && cd ..

python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8080
# abrí http://127.0.0.1:8080
```

Desarrollo del frontend con recarga en caliente:

```bash
cd web && npm run dev   # proxy /api -> http://127.0.0.1:8080
```

## Docker

```bash
docker build -t aitliber .
docker run -p 8080:8080 -v "$PWD/data:/app/data" aitliber
```

La imagen es Alpine, compila el frontend en una etapa Node y ejecuta el servidor como usuario sin privilegios.

## Configuración

| Variable | Uso |
| --- | --- |
| `AITUBER_DATA_DIR` | Carpeta de datos (SQLite, medios, renders, exportaciones). Por defecto `./data`. |
| `PORT` | Puerto HTTP (por defecto `8080`). |
| `AITUBER_TOKEN` | Protección opcional con token (`X-App-Token`). Si se define, la interfaz lo pide. |
| `PIPER_BIN`, `PIPER_MODEL` | Voz neuronal local opcional en lugar de espeak-ng. |
| `OLLAMA_URL` | Ollama local opcional para expandir narración (nunca un servicio pago). |

En **Ajustes** se configuran idioma, voz, volumen de música, estilo de subtítulos y copias de seguridad.

## Arquitectura

```
app/
  db.py         SQLite (WAL) con esquema, migraciones, ajustes, logs y copias
  script_gen.py guionista local determinista (documental / short) + Ollama opcional
  tts.py        espeak-ng / Piper y silencio informado
  media.py      tarjetas visuales, SRT/VTT, miniaturas, búsqueda en repositorios libres
  render.py     FFmpeg por escena con caché, concat, subtítulos, export ZIP
  worker.py     cola persistente en un hilo, reanudación tras reinicio
  main.py       API FastAPI y servido del frontend compilado
web/            React 19 + TypeScript + Vite (mobile-first, español)
scripts/e2e_local.py  prueba real del pipeline completo
```

Diseñado para hardware modesto: 1 CPU y 1 GB de RAM bastan para Shorts y documentales cortos; los renders largos se ejecutan en cola y se pueden reanudar.

## Pruebas

```bash
python3 scripts/e2e_local.py      # guion -> voz -> render 9:16 y 16:9 -> ZIP
cd web && npm run typecheck && npm run build
```

La prueba E2E crea un directorio de datos temporal, verifica resolución, duración, subtítulos, reutilización de escenas y contenido del ZIP, e informa cualquier aviso real del render (por ejemplo, escenas sin voz si falta espeak-ng).

## Limitaciones conocidas

- La publicación en plataformas no es automática: se entrega el paquete listo para subir.
- El material visual externo depende de la red y de las licencias de cada repositorio; siempre se registra autor, licencia y fecha de consulta.
- La música de fondo se toma de `data/music/` (el usuario aporta pistas libres).
- La voz es sintética y local; para calidad de estudio conviene instalar Piper con un modelo español.
