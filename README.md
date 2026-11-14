# AITuber Libre

Plataforma local para **investigar nichos, gestionar canales y producir documentales y Shorts** listos para revisar y publicar. Todo funciona con software libre, sin APIs de pago y sin claves: la app renderiza vídeo real con FFmpeg y voz con espeak-ng.

> Estado honesto: el guion local, la voz, los subtítulos, el render, la cola y la exportación funcionan con herramientas gratuitas. El Autopiloto descubre temas no usados mediante búsquedas en Wikipedia, guarda la fuente y los enlaces externos citados, arma escenas desde el texto recuperado y busca imágenes en Wikimedia Commons/Openverse con licencias aptas para uso comercial; si no hay red o material válido, usa tarjetas locales. Esta investigación automática es una base documental, no una verificación periodística independiente: el resultado debe revisarse antes de publicarlo. YouTube Data API v3 admite subida automática con credenciales OAuth configuradas en el servidor; TikTok no está integrado.

## Qué hace

- **Investigación**: nichos con demanda, competencia, riesgo de copyright y potencial de serie; notas con nivel de evidencia, fuente y fecha de consulta; búsqueda de imágenes con licencia.
- **Canales**: identidad, tono, idioma, formatos y cadencia.
- **Guion**: estructura narrativa de documental (8–20 min) o Short, editable escena por escena, regenerable, con búsqueda visual y transición por escena.
- **Voz**: espeak-ng local (voz española, velocidad y tono ajustables). Piper es opcional mediante `PIPER_BIN` + `PIPER_MODEL`.
- **Render**: FFmpeg horizontal 16:9, vertical 9:16 o cuadrado 1:1, con subtítulos quemados, miniaturas y música de fondo opcional.
- **Cola persistente**: un trabajo a la vez, reanudable tras reinicio y con caché por escena (no repite trabajo).
- **Entrega**: ZIP con MP4, SRT, VTT, guion en Markdown, fuentes/atribuciones en CSV, miniaturas, metadatos de publicación e informe de calidad.
- **Analítica**: importación del CSV real de YouTube Studio (no inventa métricas) y resumen con hipótesis.
- **Autopiloto**: configura nicho, canal, formato, duración, voz, aspecto, subtítulos, transiciones, resolución, FPS, música y frecuencia. Descubre temas nuevos, evita títulos ya producidos, registra fuentes y envía cada proyecto a render y entrega/publicación según la configuración. Requiere que el proceso del servidor permanezca activo para ejecutar la programación.
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
| `APP_TOKEN` o `AITUBER_TOKEN` | Protección con token (`X-App-Token`). Recomendado para cualquier despliegue público. |
| `PIPER_BIN`, `PIPER_MODEL` | Voz neuronal local opcional en lugar de espeak-ng. |
| `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET` | Credenciales OAuth de tipo TVs y dispositivos de entrada limitada. El refresh token se guarda en la base local tras conectar la cuenta. |
| `OLLAMA_URL` | Ollama local opcional para reescribir guiones a partir de las fuentes (nunca un servicio pago). |

En **Ajustes** se configuran idioma, voz, volumen de música, estilo de subtítulos, copias de seguridad y la conexión OAuth de YouTube.

### Conectar YouTube

1. En Google Cloud, creá un proyecto y habilitá **YouTube Data API v3**.
2. Creá credenciales OAuth de tipo **TVs y dispositivos de entrada limitada**.
3. En las variables de entorno de AppJet configurá `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET` y `APP_TOKEN` (o `AITUBER_TOKEN`).
4. Pegá el token de la app en **Ajustes** y tocá **Iniciar conexión**.
5. Abrí la dirección de Google que muestra Laburito, ingresá el código de usuario y autorizá la cuenta. No hace falta URL de redirección ni dominio propio.

El flujo de dispositivo usa el permiso `https://www.googleapis.com/auth/youtube`, necesario para este tipo de cliente. Google entrega un refresh token que Laburito conserva en su base de datos. Si el consentimiento OAuth queda en modo **Testing**, Google hace vencer esos refresh tokens a los 7 días; para automatización continua hay que revisar el estado de publicación y la verificación que corresponda.

## Arquitectura

```
app/
  db.py         SQLite (WAL) con esquema, migraciones, ajustes, logs y copias
  script_gen.py guionista basado en fuentes + reescritura Ollama local opcional
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

- YouTube admite publicación automática cuando la cuenta está conectada por OAuth y el servidor tiene credenciales configuradas. TikTok no está integrado.
- El material visual externo depende de la red y de las licencias de cada repositorio; siempre se registra autor, licencia y fecha de consulta.
- La música de fondo se toma de las camas libres integradas o de `data/music/` (el usuario puede aportar pistas libres).
- La voz es sintética y local; para calidad de estudio conviene instalar Piper con un modelo español.
