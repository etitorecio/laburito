# AITuber Libre

Plataforma local para **investigar nichos, gestionar canales y producir documentales y Shorts** listos para revisar y publicar. Todo funciona con software libre, sin APIs de pago: la app renderiza vídeo real con FFmpeg, usa espeak-ng como respaldo y ofrece Piper neural opcional.

> Estado honesto: el guion local, la voz, los subtítulos, el render, la cola y la exportación funcionan con herramientas gratuitas. El Autopiloto descubre temas no usados mediante búsquedas en Wikipedia, guarda la fuente y los enlaces externos citados, arma escenas desde el texto recuperado y busca imágenes en Wikimedia Commons/Openverse con licencias aptas para uso comercial; si no hay red o material válido, usa tarjetas locales. Esta investigación automática es una base documental, no una verificación periodística independiente: el resultado debe revisarse antes de publicarlo. La capa **Social Media Integration** usa integraciones oficiales por plataforma: actualmente YouTube Data API v3 con OAuth para subir Shorts; no depende de un intermediario pago. TikTok y otras redes todavía no están integradas.

## Qué hace

- **Investigación**: nichos con demanda, competencia, riesgo de copyright y potencial de serie; notas con nivel de evidencia, fuente y fecha de consulta; búsqueda de imágenes con licencia.
- **Canales**: identidad, tono, idioma, formatos y cadencia.
- **Guion**: estructura narrativa de documental (8–20 min) o Short, editable escena por escena, regenerable, con búsqueda visual y transición por escena.
- **Voz**: espeak-ng local (voz española, velocidad y tono ajustables). Piper se instala desde Ajustes con un modelo español CC0 de 63 MB; espeak-ng mantiene el acento rioplatense como alternativa.
- **Render**: FFmpeg horizontal 16:9, vertical 9:16 o cuadrado 1:1, con subtítulos quemados, miniaturas y música de fondo opcional.
- **Cola persistente**: un trabajo a la vez, reanudable tras reinicio y con caché por escena (no repite trabajo).
- **Entrega**: ZIP con MP4, SRT, VTT, guion en Markdown, fuentes/atribuciones en CSV, miniaturas, metadatos de publicación e informe de calidad.
- **Analítica**: importación del CSV real de YouTube Studio (no inventa métricas) y resumen con hipótesis.
- **Autopiloto de Shorts**: está limitado a formatos verticales 9:16 y duraciones de 15 a 180 segundos; no crea documentales ni videos horizontales. Configura nicho, canal, voz, estilo visual, subtítulos, transiciones, resolución, música y frecuencia. Descubre temas no usados, registra fuentes, crea el guion, renderiza y valida el MP4 antes de enviarlo a YouTube. Las reglas nuevas priorizan publicación automática pública en YouTube; para activarla hace falta conectar y verificar OAuth. Si falta evidencia suficiente o falla la voz/render, retiene la publicación y conserva la entrega para revisión. La huella SHA-256 evita volver a subir el mismo archivo. El workflow `autopilot-wakeup.yml` despierta la app desde GitHub Actions una vez por hora; el worker interno ejecuta las reglas vencidas. Esto reduce el riesgo de que el hosting duerma, pero no reemplaza un almacenamiento persistente: AppJet debe conservar `AITUBER_DATA_DIR` entre reinicios para no perder reglas, historial ni refresh token. La precisión del horario depende de que el proceso del servidor siga activo; si se duerme, el siguiente despertar puede retrasar la ejecución.
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
| `PIPER_BIN`, `PIPER_MODEL` | Sobrescritura manual opcional de la instalación Piper; normalmente se instala desde Ajustes. |
| `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET` | Credenciales OAuth de tipo aplicación web. El refresh token se guarda en la base local tras conectar la cuenta. |
| `OLLAMA_URL` | Ollama local opcional para reescribir guiones a partir de las fuentes (nunca un servicio pago). |

En **Ajustes** se configuran idioma, voz, volumen de música, estilo de subtítulos, copias de seguridad y **Social Media Integration · YouTube**, la conexión OAuth oficial.

### Conectar YouTube

1. En Google Cloud, creá un proyecto y habilitá **YouTube Data API v3**.
2. Configurá la pantalla de consentimiento; si está en Testing, agregá tu cuenta como usuario de prueba. Creá credenciales OAuth de tipo **Aplicación web** y agregá `https://developers.google.com/oauthplayground` como URI de redirección autorizada.
3. En las variables de entorno de AppJet configurá `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET` y `APP_TOKEN` (o `AITUBER_TOKEN`).
4. Abrí el [OAuth 2.0 Playground oficial](https://developers.google.com/oauthplayground). En el engranaje activá **Use your own OAuth credentials**, pegá tu Client ID y Client Secret, seleccioná flujo **Server-side**, acceso **Offline** y forzá la pantalla de consentimiento.
5. En Step 1 solicitá `https://www.googleapis.com/auth/youtube.upload` y `https://www.googleapis.com/auth/youtube.readonly`. Autorizá y canjeá el código por tokens.
6. Copiá el **Refresh token** y pegalo en **Ajustes → Social Media Integration · YouTube**. Laburito lo guarda en el servidor; después podés verificar el nombre del canal.

Usá tus propias credenciales en OAuth Playground: su cliente de prueba revoca refresh tokens a las 24 horas. Si la pantalla de consentimiento de Google permanece en modo **Testing**, los tokens de aplicaciones externas pueden vencer a los 7 días. Para automatización continua hay que revisar el estado de publicación y la verificación que Google exija.

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

- El Autopiloto solo publica Shorts verticales 9:16 de hasta 180 segundos en YouTube. La portada personalizada no se puede fijar mediante la API para Shorts; se guarda localmente para uso manual. TikTok no está integrado.
- El material visual externo depende de la red y de las licencias de cada repositorio; siempre se registra autor, licencia y fecha de consulta.
- La música de fondo se toma de las camas libres integradas o de `data/music/` (el usuario puede aportar pistas libres).
- La voz es sintética y local; para una voz neural local se puede instalar Piper DaveFX (España, CC0) desde Ajustes; la voz rioplatense espeak sigue disponible.
