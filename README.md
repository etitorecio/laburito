# AITuber Libre

Reconstrucción libre y local de la experiencia de IATuber, enfocada en **Shorts en español**. Interfaz y opciones en español, sin planes, suscripciones, tokens de generación ni créditos comerciales. La voz, los subtítulos, los estilos visuales, las animaciones locales y el render se procesan con software libre en tu PC.

> Estado honesto: el guion local, la voz, los subtítulos, el render, la cola y la exportación funcionan con herramientas gratuitas. El Autopiloto combina señales relacionadas del RSS público de Google Trends Argentina con búsquedas de temas no usados en Wikipedia y resúmenes académicos de OpenAlex, guarda las fuentes y enlaces externos citados, y arma escenas desde el texto recuperado y busca imágenes en Wikimedia Commons/Openverse con licencias aptas para uso comercial; si no hay red o material válido, usa tarjetas locales. Esta investigación automática es una base documental, no una verificación periodística independiente: el resultado debe revisarse antes de publicarlo. La publicación automática disponible es YouTube mediante OAuth oficial. No requiere tokens de IA, pero Google sí exige autorizar tu cuenta y aplicar la cuota gratuita de YouTube Data API; esa cuota no se puede eliminar ni prometer como infinita. TikTok e Instagram todavía no tienen publicación automática.

## Qué hace

- **Investigación**: nichos con demanda, competencia, riesgo de copyright y potencial de serie; notas con nivel de evidencia, fuente y fecha de consulta; búsqueda de imágenes con licencia.
- **Canales**: identidad, tono, idioma, formatos y cadencia.
- **Guion IA local**: Ollama descarga una vez el modelo Qwen 2.5 1.5B (Apache 2.0, aprox. 1 GB) y lo ejecuta en tu PC para expandir los guiones; no usa API keys, tokens de generación ni créditos. Si el modelo no está disponible, conserva el guion estructurado de respaldo.
- **Voz**: tarjetas de voces exclusivamente españolas, con muestra de audio antes de elegir. espeak-ng funciona localmente; Piper neural español se puede instalar sin claves ni pagos.
- **Demostraciones**: los 13 estilos de subtítulos, los movimientos de escena y los 10 tratamientos visuales tienen vistas previas generadas por FFmpeg, el mismo motor del video final.
- **Render**: FFmpeg para Shorts verticales 9:16, con subtítulos quemados, miniaturas y música de fondo opcional.
- **Cola persistente**: un trabajo a la vez, reanudable tras reinicio y con caché por escena (no repite trabajo).
- **Entrega**: ZIP con MP4, SRT, VTT, guion en Markdown, fuentes/atribuciones en CSV, miniaturas, metadatos de publicación e informe de calidad.
- **Analítica**: importación del CSV real de YouTube Studio (no inventa métricas) y resumen con hipótesis.
- **Autopiloto de Shorts**: asistente de una pantalla por paso: nicho, voz, música, apariencia, subtítulos, publicación, calendario y confirmación. Configurá una vez y dejá la PC encendida para producir y publicar según el horario. El modo automático rota las pistas locales. Antes de subir, valida el MP4 y conserva los errores en la cola. YouTube requiere OAuth oficial y está sujeto a la cuota gratuita de Google; no se puede quitar esa cuota ni garantizar publicaciones ilimitadas.
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

## Modo local gratuito y persistente (recomendado)

Para usar Laburito sin pagar hosting ni Supabase, ejecutalo en una PC propia. Docker conserva la base, los videos y los trabajos en la carpeta `./data`; el Autopiloto sigue funcionando mientras la PC esté encendida, conectada a Internet y sin suspensión automática. Podés abrir la interfaz desde el celular conectado a la misma red Wi-Fi usando la IP local de la PC.

En Windows, instalá Docker Desktop y activá su inicio automático al iniciar sesión. Después, hacé doble clic en `start_windows.bat`: construye la imagen, inicia el contenedor y abre la interfaz. También imprime la dirección local para entrar desde el celular por Wi-Fi. No necesitás claves ni tokens de IA para generar videos; mantené el acceso limitado a tu red local y no expongas el puerto a Internet. La primera compilación puede tardar y el primer inicio descarga el modelo local de lenguaje Qwen 2.5 1.5B (aprox. 1 GB). Después queda guardado en `./ollama` y no se vuelve a descargar.
Para que se cumpla el calendario, dejá la PC encendida y evitá que entre en suspensión; Docker Desktop y el contenedor deben permanecer activos. Si la PC se apaga, el worker recupera la programación pendiente cuando vuelve a arrancar.

Si preferís hacerlo manualmente:

```powershell
Copy-Item .env.example .env
notepad .env
docker compose up -d --build
```

Después abrí `http://localhost:8080` en la PC. Desde el celular usá `http://IP-LOCAL-DE-LA-PC:8080`. Para detenerlo: `docker compose down`. Para volver a iniciarlo: `docker compose up -d`. No borres la carpeta `data`: contiene los proyectos, la programación, la autorización y los renders. No compartas el puerto en Internet sin HTTPS y protección adicional.

La imagen final usa Debian slim (glibc, necesaria para Piper/ONNX Runtime), compila FFmpeg y el frontend en etapas separadas, y ejecuta el servidor como usuario sin privilegios. El primer build puede tardar porque compila FFmpeg; los siguientes arranques reutilizan la imagen.


## Configuración

| Variable | Uso |
| --- | --- |
| `AITUBER_DATA_DIR` | Carpeta de datos (SQLite, medios, renders, exportaciones). Por defecto `./data`. |
| `AITUBER_LOCAL_PERSISTENT` | Marcador de diagnóstico para un volumen local persistente (lo configura Docker Compose). |
| `PORT` | Puerto HTTP (por defecto `8080`). |
| `PIPER_BIN`, `PIPER_MODEL` | Sobrescritura manual opcional de la instalación Piper; normalmente se instala desde Ajustes. |
| `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET` | Credenciales OAuth de tipo aplicación web. La autorización de YouTube se guarda en la base local tras conectar la cuenta. |
| `YOUTUBE_REDIRECT_URI` | URI de callback OAuth opcional; por defecto se calcula con el dominio actual. |
| `SUPABASE_URL` | Opcional para copias remotas en despliegues alojados; no se necesita en Docker local. |
| `SUPABASE_SERVICE_ROLE_KEY` | Clave privada opcional para copias remotas; no se necesita en Docker local. |
| `SUPABASE_STORAGE_BUCKET` | Nombre opcional del bucket privado de backups (por defecto `laburito-private-backups`); se crea automáticamente. |

En **Ajustes** se configuran voz, música, estilos visuales, subtítulos, movimientos, almacenamiento local y la conexión OAuth oficial de YouTube.

### Guionista IA local sin coste

Para reescritura de guiones con un modelo local, instalá [Ollama](https://ollama.com/download), ejecutá `ollama pull llama3.2` y guardá la URL en Ajustes → Ollama local. Con Docker Desktop para Windows usá `http://host.docker.internal:11434`; si ejecutás Laburito directamente en la PC, usá `http://127.0.0.1:11434`. Sin Ollama, el autopiloto conserva el guionista gratuito basado en fuentes.

### Conectar YouTube

1. En Google Cloud, creá un proyecto y habilitá **YouTube Data API v3**.
2. Configurá la pantalla de consentimiento y agregá tu cuenta como usuario de prueba si la app está en Testing. Creá credenciales OAuth de tipo **Aplicación web**.
3. En **Ajustes → Conexión de YouTube**, copiá la URI de callback que muestra Laburito y agregala como URI de redirección autorizada en Google Cloud. En AppJet será `https://TU-EDGE-URL/api/youtube/callback`; en Docker local, `http://localhost:8080/api/youtube/callback`.
4. En el archivo `.env` local configurá `YOUTUBE_CLIENT_ID` y `YOUTUBE_CLIENT_SECRET`. El modo local no pide contraseña ni tokens de acceso; no expongas el puerto a Internet. `YOUTUBE_REDIRECT_URI` es opcional si necesitás fijar manualmente la URI exacta.
5. Volvé a Ajustes y tocá **Conectar canal con Google**. Autorizá el canal. Laburito completa la autorización y guarda el permiso localmente; después comprobá el nombre del canal.

Si la pantalla de consentimiento permanece en modo **Testing**, Google puede revocar el permiso de aplicaciones externas después de 7 días. Para automatización continua, revisá el estado de publicación de la app OAuth y los requisitos de verificación que Google indique. El OAuth Playground queda solo como alternativa manual avanzada.


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

Optimizado para equipos modestos con CPU: las imágenes con movimiento, subtítulos, estilos visuales y el esqueleto 2.5D se procesan localmente. En una notebook de 12 GB de RAM conviene usar 720p/1080p y renderizar un trabajo a la vez. El modelo Qwen 2.5 1.5B funciona por CPU, pero la generación de guiones puede ser lenta.

## Pruebas

```bash
python3 scripts/e2e_local.py      # guion -> voz -> render 9:16 y 16:9 -> ZIP
cd web && npm run typecheck && npm run build
```

La prueba E2E crea un directorio de datos temporal, verifica resolución, duración, subtítulos, reutilización de escenas y contenido del ZIP, e informa cualquier aviso real del render (por ejemplo, escenas sin voz si falta espeak-ng).

## Despliegue y uso real

La opción recomendada es **Docker local en tu PC**, con la carpeta `./data` persistente. No necesitás Supabase, AppJet ni un hosting pago. La computadora debe permanecer encendida y sin suspensión para que el Autopiloto trabaje; podés entrar desde el celular por la IP local de la PC. El hosting gratuito efímero no es adecuado para conservar una cola y publicar a diario sin un almacenamiento externo.

## Limitaciones conocidas

- El tipo "Imágenes con movimiento" usa imágenes de archivo con paneo/zoom; no es generación de imágenes IA. "Esqueleto animado" produce un personaje 2.5D procedural local, no un modelo 3D generativo. "Videos de archivo", Minecraft y Subway Surfers funcionan con cinco clips propios o autorizados cargados en sus bibliotecas locales. "Video IA de movimiento completo" permanece desactivado: los modelos abiertos de video requieren recursos de GPU/VRAM que no son realistas para una notebook con gráficos integrados.
- El material visual externo depende de la red y de las licencias de cada repositorio; siempre se registra autor, licencia y fecha de consulta. La subida a YouTube registra el ID devuelto por la API y consulta `videos.list` para confirmar su presencia; el procesamiento de YouTube puede continuar después de que termine la tarea.\n- La persistencia de Supabase es obligatoria para autopublicar desde AppJet Free, porque no incluye disco virtual persistente. En Docker local se usa el volumen `./data` y Supabase no es necesario. El backup remoto es una copia de SQLite, no una base multiinstancia; ejecutá una sola instancia de worker para evitar concurrencia.
- Es una instalación de un solo propietario: la instancia local no tiene autenticación multiusuario y el estado OAuth/SQLite no está aislado por usuario. No la ofrezcas como SaaS compartido ni guardes canales de varios amigos en la misma instancia. Para compartirla hoy, cada persona debe desplegar su propia copia; falta autenticación multiusuario y aislamiento de credenciales. No la expongas directamente a Internet.
- La música de fondo se toma de las camas libres integradas o de `data/music/` (el usuario puede aportar pistas libres).
- La voz es sintética y local; para una voz neural local se puede instalar Piper DaveFX (España, CC0) desde Ajustes; la voz rioplatense espeak sigue disponible.
