# AITuber Libre

Plataforma local para **investigar nichos, gestionar canales y producir documentales y Shorts** listos para revisar y publicar. Todo funciona con software libre, sin APIs de pago: la app renderiza vídeo real con FFmpeg, usa espeak-ng como respaldo y ofrece Piper neural opcional.

> Estado honesto: el guion local, la voz, los subtítulos, el render, la cola y la exportación funcionan con herramientas gratuitas. El Autopiloto combina señales relacionadas del RSS público de Google Trends Argentina con búsquedas de temas no usados en Wikipedia y resúmenes académicos de OpenAlex, guarda las fuentes y enlaces externos citados, y arma escenas desde el texto recuperado y busca imágenes en Wikimedia Commons/Openverse con licencias aptas para uso comercial; si no hay red o material válido, usa tarjetas locales. Esta investigación automática es una base documental, no una verificación periodística independiente: el resultado debe revisarse antes de publicarlo. La capa **Social Media Integration** usa integraciones oficiales por plataforma: actualmente YouTube Data API v3 con OAuth para subir Shorts; no depende de un intermediario pago. TikTok y otras redes todavía no están integradas.

## Qué hace

- **Investigación**: nichos con demanda, competencia, riesgo de copyright y potencial de serie; notas con nivel de evidencia, fuente y fecha de consulta; búsqueda de imágenes con licencia.
- **Canales**: identidad, tono, idioma, formatos y cadencia.
- **Guion**: estructura narrativa de documental (8–20 min) o Short, editable escena por escena, regenerable, con búsqueda visual y transición por escena.
- **Voz**: espeak-ng local (voz española, velocidad y tono ajustables). Piper se instala desde Ajustes con un modelo español CC0 de 63 MB; espeak-ng mantiene el acento rioplatense como alternativa.
- **Render**: FFmpeg horizontal 16:9, vertical 9:16 o cuadrado 1:1, con subtítulos quemados, miniaturas y música de fondo opcional.
- **Cola persistente**: un trabajo a la vez, reanudable tras reinicio y con caché por escena (no repite trabajo).
- **Entrega**: ZIP con MP4, SRT, VTT, guion en Markdown, fuentes/atribuciones en CSV, miniaturas, metadatos de publicación e informe de calidad.
- **Analítica**: importación del CSV real de YouTube Studio (no inventa métricas) y resumen con hipótesis.
- **Autopiloto de Shorts**: está limitado a formatos verticales 9:16 y duraciones de 15 a 180 segundos; no crea documentales ni videos horizontales. Configura nicho, canal, voz, estilo visual, subtítulos, transiciones, resolución, música y frecuencia. Descubre temas no usados, registra fuentes, crea el guion, renderiza y valida el MP4 antes de enviarlo a YouTube. Las reglas nuevas priorizan publicación automática pública en YouTube; para activarla hace falta conectar y verificar OAuth. Si falta evidencia suficiente o falla la voz/render, retiene la publicación y conserva la entrega para revisión. La huella SHA-256 evita volver a subir el mismo archivo. El workflow `autopilot-wakeup.yml`, instalado también en la rama predeterminada `main` (requisito de GitHub para los cron), despierta la app desde GitHub Actions cada 5 minutos; el worker interno ejecuta las reglas vencidas. El workflow exige la variable de repositorio `LABURITO_URL` con la URL Edge real de la rama `appjet`; ya no cae silenciosamente en la URL dev de preview. GitHub puede retrasar los cron y esto no es un SLA de publicación exacta. El workflow reduce retrasos cuando la app duerme, pero no conserva datos por sí solo. AppJet Free no incluye disco virtual persistente: si configurás `SUPABASE_URL` y `SUPABASE_SERVICE_ROLE_KEY`, Laburito restaura y sincroniza SQLite comprimido en un bucket privado de Supabase (después de cambios de configuración y tareas, y además cada 15 minutos); también conserva el MP4 pendiente hasta que YouTube lo recibe y elimina esa copia después de guardar el estado publicado. La autopublicación se bloquea si no hay almacenamiento durable. Sin Supabase, las reglas, trabajos, historial y refresh token pueden perderse al reemplazar el contenedor. La clave service-role debe guardarse únicamente como secreto del servidor; nunca en el frontend. La precisión del horario depende de que el proceso del servidor siga activo; si se duerme, el siguiente despertar puede retrasar la ejecución.
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

En Windows, instalá Docker Desktop y activá su inicio automático al iniciar sesión. Después, hacé doble clic en `start_windows.bat`: crea un `APP_TOKEN` aleatorio si hace falta, construye la imagen, inicia el contenedor y abre la interfaz. También imprime la dirección local para entrar desde el celular por Wi-Fi. La primera compilación puede tardar.
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
| `APP_TOKEN` o `AITUBER_TOKEN` | Protección con token (`X-App-Token`). Recomendado para cualquier despliegue público. |
| `PIPER_BIN`, `PIPER_MODEL` | Sobrescritura manual opcional de la instalación Piper; normalmente se instala desde Ajustes. |
| `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET` | Credenciales OAuth de tipo aplicación web. El refresh token se guarda en la base local tras conectar la cuenta. |
| `YOUTUBE_REDIRECT_URI` | URI de callback OAuth opcional; por defecto se calcula con el dominio actual. |
| `SUPABASE_URL` | URL del proyecto Supabase; requerida para autopublicar en AppJet Free, opcional en Docker local con volumen persistente. |
| `SUPABASE_SERVICE_ROLE_KEY` | Clave service-role privada; requerida junto con `SUPABASE_URL` en AppJet Free, solo en variables del servidor. |
| `SUPABASE_STORAGE_BUCKET` | Nombre opcional del bucket privado de backups (por defecto `laburito-private-backups`); se crea automáticamente. |

En **Ajustes** se configuran idioma, voz, volumen de música, estilo de subtítulos, copias de seguridad y **Social Media Integration · YouTube**, la conexión OAuth oficial.

### Guionista IA local sin coste

Para reescritura de guiones con un modelo local, instalá [Ollama](https://ollama.com/download), ejecutá `ollama pull llama3.2` y guardá la URL en Ajustes → Ollama local. Con Docker Desktop para Windows usá `http://host.docker.internal:11434`; si ejecutás Laburito directamente en la PC, usá `http://127.0.0.1:11434`. Sin Ollama, el autopiloto conserva el guionista gratuito basado en fuentes.

### Conectar YouTube

1. En Google Cloud, creá un proyecto y habilitá **YouTube Data API v3**.
2. Configurá la pantalla de consentimiento y agregá tu cuenta como usuario de prueba si la app está en Testing. Creá credenciales OAuth de tipo **Aplicación web**.
3. En **Ajustes → Social Media Integration · YouTube**, copiá la URI de callback que muestra Laburito y agregala como URI de redirección autorizada en Google Cloud. En AppJet será `https://TU-EDGE-URL/api/youtube/callback`; en Docker local, `http://localhost:8080/api/youtube/callback`.
4. En las variables de entorno de AppJet o en el archivo `.env` local configurá `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET` y `APP_TOKEN`. `YOUTUBE_REDIRECT_URI` es opcional si necesitás fijar manualmente la URI exacta.
5. Volvé a Ajustes y tocá **Conectar canal con Google**. Autorizá el canal. Laburito canjea el código y guarda el refresh token en el servidor; después comprobá el nombre del canal.

Si la pantalla de consentimiento permanece en modo **Testing**, Google puede hacer vencer los refresh tokens de aplicaciones externas después de 7 días. Para automatización continua, revisá el estado de publicación de la app OAuth y los requisitos de verificación que Google indique. El OAuth Playground queda solo como alternativa manual avanzada.


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

## Despliegue y uso real

La URL `*.dev.ap-jt.com` es solo un endpoint de desarrollo/preview. AppJet también ofrece un endpoint Edge en el plan Free, sin vencimiento por edad. Para probar Laburito desde Android, copiá la URL Edge desde Settings → Overview y guardala como variable de repositorio `LABURITO_URL` en [GitHub → Variables](https://github.com/etitorecio/laburito/settings/variables/actions). El workflow de GitHub Actions despierta ese endpoint cada cinco minutos y el health check reanima el worker si se detuvo. AppJet Free no incluye disco virtual: conectá Supabase y configurá `SUPABASE_URL` y `SUPABASE_SERVICE_ROLE_KEY` en las variables del servidor; las cuotas y condiciones propias de Supabase siguen aplicando. **Límite importante:** AppJet Free asigna 1 GB de RAM y 1 vCPU por app, no incluye disco virtual y su documentación dice que el hosting está pensado para desarrollo, pruebas y compartir, no para producción con datos reales. FFmpeg + Piper pueden alcanzar esos límites. No lo uses como SaaS comercial alojado allí. Para el autopiloto diario gratuito de una sola cuenta, preferí Docker local con volumen persistente; para producción real, hace falta un hosting de producción.

## Limitaciones conocidas

- El Autopiloto solo publica Shorts verticales 9:16 de hasta 180 segundos en YouTube. Actualmente el motor visual usa imágenes de archivo con paneo/zoom y tarjetas locales de respaldo: Full Motion AI Video, Skeleton Video y gameplay de Minecraft/Subway Surfers aparecen como opciones de referencia, pero todavía no producen clips reales. Las miniaturas del selector son ilustrativas; para gameplay hacen falta clips propios o con licencia. La portada personalizada no se puede fijar mediante la API para Shorts; se guarda localmente para uso manual. TikTok no está integrado.
- El material visual externo depende de la red y de las licencias de cada repositorio; siempre se registra autor, licencia y fecha de consulta. La subida a YouTube registra el ID devuelto por la API y consulta `videos.list` para confirmar su presencia; el procesamiento de YouTube puede continuar después de que termine la tarea.\n- La persistencia de Supabase es obligatoria para autopublicar desde AppJet Free, porque no incluye disco virtual persistente. En Docker local se usa el volumen `./data` y Supabase no es necesario. El backup remoto es una copia de SQLite, no una base multiinstancia; ejecutá una sola instancia de worker para evitar concurrencia.
- Es una instalación de un solo propietario: `APP_TOKEN` protege la instancia completa y el estado OAuth/SQLite no está aislado por usuario. No la ofrezcas como SaaS compartido ni guardes canales de varios amigos en la misma instancia. Para compartirla hoy, cada persona debe desplegar su propia copia; falta autenticación multiusuario y aislamiento de credenciales.
- La música de fondo se toma de las camas libres integradas o de `data/music/` (el usuario puede aportar pistas libres).
- La voz es sintética y local; para una voz neural local se puede instalar Piper DaveFX (España, CC0) desde Ajustes; la voz rioplatense espeak sigue disponible.
