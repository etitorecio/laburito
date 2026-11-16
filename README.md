# AITuber Libre

Reconstrucción libre y local de la experiencia de IATuber, para **Shorts y documentales largos en español**. Interfaz y opciones en español, con un asistente de configuración por pasos, sin planes, suscripciones, tokens de generación ni créditos comerciales. La voz, los subtítulos, los estilos visuales, las animaciones locales y el render se procesan con software libre en tu PC.

> Estado honesto: el guion local, la voz, los subtítulos, el render, la cola y la exportación funcionan con herramientas gratuitas. El Autopiloto combina señales relacionadas del RSS público de Google Trends Argentina con búsquedas de temas no usados en Wikipedia y resúmenes académicos de OpenAlex, guarda las fuentes y enlaces externos citados, y arma escenas desde el texto recuperado y busca imágenes en Wikimedia Commons/Openverse con licencias aptas para uso comercial; si no hay red o material válido, usa tarjetas locales. Esta investigación automática es una base documental, no una verificación periodística independiente: el resultado debe revisarse antes de publicarlo. La publicación en YouTube se inicia manualmente después de revisar el render, mediante OAuth oficial. No requiere tokens de IA, pero Google sí exige autorizar tu cuenta y aplicar la cuota gratuita de YouTube Data API; esa cuota no se puede eliminar ni prometer como infinita. No se publica ningún video sin aprobación explícita.

## Qué hace

- **Investigación**: nichos con demanda, competencia, riesgo de copyright y potencial de serie; notas con nivel de evidencia, fuente y fecha de consulta; búsqueda de imágenes con licencia.
- **Canales**: identidad, tono, idioma, formatos y cadencia.
- **Guion IA local**: Ollama descarga una vez el modelo Qwen 2.5 1.5B (Apache 2.0, aprox. 1 GB) y lo ejecuta en tu PC para expandir los guiones; no usa API keys, tokens de generación ni créditos. Si el modelo no está disponible, conserva el guion estructurado de respaldo.
- **Guion propio a video**: también podés pegar un guion completo; Laburito lo divide en escenas, conserva la narración y continúa con voz, visuales, subtítulos, música y render. No requiere IA externa.
- **Editor de escenas**: proyectos vacíos, escenas manuales, línea de tiempo con selección y reordenamiento por arrastre, narración editable y escuchable antes del render, carga de imágenes propias, búsqueda de visuales con licencia, vista de cada imagen, movimiento por escena y regeneración individual. Si Ollama/Qwen está disponible, la regeneración usa IA local; si no, informa y aplica una variante de respaldo sin servicios pagos.
- **Voz**: tarjetas de voces exclusivamente españolas, con muestra de audio antes de elegir.
- **Rendimiento local**: 720p y 25 FPS por defecto para reducir carga en CPU; se puede subir a 1080p o más cuando el equipo lo permita. espeak-ng funciona localmente y Piper neural DaveFX se descarga automáticamente al iniciar (63 MB), sin claves ni pagos.
- **Demostraciones**: los 13 estilos de subtítulos, los movimientos de escena y los 10 tratamientos visuales tienen vistas previas generadas por FFmpeg, el mismo motor del video final.
- **Render**: FFmpeg para Shorts verticales 9:16, con subtítulos quemados, miniaturas y música de fondo opcional.
- **Frutinovelas**: plantilla vertical de ficción episódica con personajes recurrentes definidos por el usuario, escenas de melodrama, traición, giro y cliffhanger para continuar la serie. Dibuja ilustraciones 2D procedurales originales del mismo elenco frutal en cada escena, sin IA externa ni créditos.
- **Cola persistente**: un trabajo a la vez, reanudable tras reinicio y con caché por escena (no repite trabajo).
- **Entrega**: ZIP con MP4, SRT, VTT, guion en Markdown, fuentes/atribuciones en CSV, miniaturas, metadatos de publicación e informe de calidad.
- **Analítica**: importación del CSV real de YouTube Studio (no inventa métricas) y resumen con hipótesis.
- **Autopiloto de videos**: asistente de ocho pantallas al estilo IATuber: nicho, idioma/voz (español fijo), música, apariencia, subtítulos, destino, calendario y tipo/frecuencia de publicación. Hasta cinco pistas propias, rotación secuencial, volumen ajustable, miniaturas opcionales y referencia visual por análisis local de paleta. Configurá una vez y dejá la PC encendida para producir según el horario. Antes de publicar, valida el MP4 y conserva los errores en la cola. La subida a YouTube requiere aprobación manual, OAuth oficial y está sujeta a la cuota gratuita de Google; no se puede quitar esa cuota ni garantizar publicaciones ilimitadas.
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

En Windows, instalá Docker Desktop y activá su inicio automático al iniciar sesión. Después, hacé doble clic en `start_windows.bat`: construye la imagen, inicia el contenedor y abre la interfaz. También imprime la dirección local para entrar desde el celular por Wi-Fi. No necesitás claves ni tokens de IA para generar videos; mantené el acceso limitado a tu red local y no expongas el puerto a Internet. La primera compilación puede tardar y el primer inicio descarga el modelo local de lenguaje Qwen 2.5 1.5B (aprox. 1 GB) y la voz neural española Piper (63 MB). Después queda guardado en `./ollama` y no se vuelve a descargar.
Para que se cumpla el calendario, dejá la PC encendida y evitá que entre en suspensión; Docker Desktop y el contenedor deben permanecer activos. Si la PC se apaga, el worker recupera la programación pendiente cuando vuelve a arrancar.

Si preferís hacerlo manualmente:

```powershell
Copy-Item .env.example .env
notepad .env
docker compose up -d --build
```

Después abrí `http://localhost:8080` en la PC. Desde el celular usá `http://IP-LOCAL-DE-LA-PC:8080`. Para detenerlo: `docker compose down`. Para volver a iniciarlo: `docker compose up -d`. No borres la carpeta `data`: contiene los proyectos, la programación, la autorización y los renders. No compartas el puerto en Internet sin HTTPS y protección adicional.

La imagen final usa Debian slim (glibc, necesaria para Piper/ONNX Runtime), instala el FFmpeg mantenido por Debian y compila el frontend en una etapa separada. El servidor corre como usuario sin privilegios y evita compilar FFmpeg desde cero.


## Configuración

| Variable | Uso |
| --- | --- |
| `AITUBER_DATA_DIR` | Carpeta de datos (SQLite, medios, renders, exportaciones). Por defecto `./data`. |
| `AITUBER_LOCAL_PERSISTENT` | Marcador de diagnóstico para un volumen local persistente (lo configura Docker Compose). |
| `PORT` | Puerto HTTP (por defecto `8080`). |
| `PIPER_BIN`, `PIPER_MODEL` | Sobrescritura manual opcional de la instalación Piper; normalmente se instala automáticamente al iniciar. |
| `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET` | Credenciales OAuth de tipo aplicación web. La autorización de YouTube se guarda en la base local tras conectar la cuenta. |
| `YOUTUBE_REDIRECT_URI` | URI de callback OAuth opcional; por defecto se calcula con el dominio actual. |

En **Ajustes** se configuran voz, música, estilos visuales, subtítulos, movimientos y almacenamiento local. La conexión OAuth de YouTube se administra desde **Cuentas**.

### Guionista IA local sin coste

La instalación Docker incluye Ollama y descarga automáticamente Qwen 2.5 1.5B (Apache 2.0, aproximadamente 1 GB) para reescribir los guiones en español. No tenés que instalar ni configurar el modelo a mano. Si la descarga falla o ejecutás la app sin Docker, el autopiloto conserva el guionista gratuito basado en fuentes.

### Conectar YouTube

1. En Google Cloud, creá un proyecto y habilitá **YouTube Data API v3**.
2. Configurá la pantalla de consentimiento y agregá tu cuenta como usuario de prueba si la app está en Testing. Creá credenciales OAuth de tipo **Aplicación web**.
3. Abrí **Cuentas** en Laburito y copiá la URI de redirección exacta que aparece en el aviso de configuración. Agregala como URI de redirección autorizada en Google Cloud.
4. En el archivo `.env` local configurá `YOUTUBE_CLIENT_ID` y `YOUTUBE_CLIENT_SECRET`; en un hosting, agregalas como variables/secretos del servidor. `YOUTUBE_REDIRECT_URI` es opcional si necesitás fijar manualmente la URI exacta. Reiniciá la aplicación.
5. Volvé a **Cuentas** y conectá primero la cuenta Google del canal Historias y después la cuenta del canal Frutinovelas. Cada autorización se guarda por separado. No compartas el secreto de cliente ni lo pegues en el chat.

Si la pantalla de consentimiento permanece en modo **Testing**, Google puede revocar el permiso de aplicaciones externas después de 7 días. Para automatización continua, revisá el estado de publicación de la app OAuth y los requisitos de verificación que Google indique. El OAuth Playground queda solo como alternativa manual avanzada.


## Arquitectura

```
app/
  db.py         SQLite (WAL) con esquema, migraciones, ajustes, logs y copias
  script_gen.py guionista basado en fuentes + reescritura con Qwen local
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

- El tipo "Imágenes con movimiento" usa imágenes de archivo con paneo/zoom; no es generación de imágenes IA. "Esqueleto animado" produce un personaje 2.5D procedural local, no un modelo 3D generativo. "Videos de archivo", Minecraft y Subway Surfers stock footage requiere cinco clips; Minecraft y Subway Surfers requieren uno como mínimo y permiten hasta cinco clips propios o autorizados en sus bibliotecas locales. "Video IA de movimiento completo" permanece desactivado: los modelos abiertos de video requieren recursos de GPU/VRAM que no son realistas para una notebook con gráficos integrados.
- El material visual externo depende de la red y de las licencias de cada repositorio; siempre se registra autor, licencia y fecha de consulta. La subida a YouTube registra el ID devuelto por la API y consulta `videos.list` para confirmar su presencia; el procesamiento de YouTube puede continuar después de que termine la tarea.
- El almacenamiento local persistente se conserva en `./data`; no se necesita Supabase ni una base de datos externa.
- Es una instalación de un solo propietario: la instancia local no tiene autenticación multiusuario y el estado OAuth/SQLite no está aislado por usuario. No la ofrezcas como SaaS compartido ni guardes canales de varios amigos en la misma instancia. Para compartirla hoy, cada persona debe desplegar su propia copia; falta autenticación multiusuario y aislamiento de credenciales. No la expongas directamente a Internet.
- La música de fondo se toma de las camas libres integradas o de `data/music/` (el usuario puede aportar pistas libres).
- La voz es sintética y local; Piper DaveFX (España, CC0) se descarga automáticamente en el primer inicio; la voz rioplatense espeak sigue disponible.


### Fuentes gratuitas de gameplay

- Subway Surfers: el canal oficial publica dos videos marcados `FREE TO USE`: [vertical](https://www.youtube.com/watch?v=QPW3XwBoQlw) y [horizontal](https://www.youtube.com/watch?v=i0M4ARe9v0Y). **No asumir que esa etiqueta es una licencia comercial universal**: las [condiciones generales de SYBO](https://sybogames.com/terms-of-service/) reservan los derechos del juego y restringen la publicación/exhibición pública y los usos comerciales no autorizados. Para monetizar, conseguir permiso escrito específico de SYBO y conservarlo; si no, usar un runner genérico con licencia comercial explícita.
- Minecraft: la opción más sólida es grabar una partida propia y cumplir las [Usage Guidelines oficiales de Mojang](https://www.minecraft.net/en-us/usage-guidelines). Como alternativas, [Orbital](https://www.youtube.com/watch?v=u7kdVe8q5zs) declara que permite monetizar su grabación y pide crédito, y [Addy en Vimeo](https://vimeo.com/1005854698) declara que permite descargar y reutilizar sus grabaciones y pide crédito. Esos permisos cubren la grabación de cada creador, no reemplazan las reglas de Mojang; usá solo descargas habilitadas por el creador.
- El selector de gameplay muestra estas fuentes y permite empezar con un clip, con hasta cinco por biblioteca. La autorización de un creador para una grabación no sustituye las reglas del titular del juego. No se descarga material automáticamente desde YouTube ni se eluden sus restricciones.


## Fábricas de YouTube Shorts

Las dos fábricas principales son **Historias estilo Reddit** y **Frutinovelas**. Ambas producen exclusivamente video vertical 9:16, con una duración máxima de 180 segundos. La interfaz de creación y el Autopiloto ofrecen esas dos plantillas; el backend vuelve a validar formato, duración y correspondencia entre cada fábrica y su canal para evitar cruces accidentales.
