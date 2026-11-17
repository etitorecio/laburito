# Matriz de paridad funcional con AITuber.app

**Objetivo:** reproducir la experiencia y las capacidades útiles de AITuber.app sin copiar código, marca ni recursos propietarios, manteniendo costo obligatorio $0 y procesamiento local cuando sea viable.

**Fecha de auditoría:** 2026-11-17  
**Rama auditada:** `appjet`

Estados:
- **Implementada:** existe en Laburito y hay pruebas o código verificable.
- **Parcial:** existe una alternativa funcional, pero no alcanza la capacidad/experiencia completa de AITuber.
- **Ausente:** no existe una implementación utilizable identificada.
- **Bloqueada:** el código existe, pero falta una configuración externa para que funcione en el despliegue correspondiente.

## Matriz

| Capacidad de AITuber | Estado Laburito | Evidencia / diferencia |
|---|---|---|
| Inicio mobile-first y creación desde una idea breve | Parcial | El bloque «Decilo y se hace» ahora es el primer bloque de Inicio, antes del hero; ofrece accesos directos Shorts, Historias, Frutinovela y Documentales, orden natural breve, canal opcional y botón Crear. Después de crear, abre Cola de trabajo con el progreso real; el editor solo se abre cuando el usuario toca «Abrir». Interpreta comandos comunes con parser determinista; no es un agente conversacional multimodal. La compilación web está probada, pero falta prueba física en Android. |
| Pegar un guion propio y convertirlo a video | Implementada | Endpoint de guion y pipeline de escenas existente. |
| Shorts verticales | Implementada | Plantillas verticales, subtítulos, voz, visuales y render FFmpeg. |
| Documentales largos | Parcial | Pipeline horizontal disponible, con duración limitada a 20 minutos; falta comparar calidad/variedad visual con el motor comercial. |
| Frutinovelas episódicas | Implementada | Plantilla propia, personajes recurrentes, recapitulación de las últimas escenas y 1.728 combinaciones de premisas para evitar repetir episodios recientes; conserva cliffhangers. |
| Historias estilo Reddit | Implementada | Fábrica interna con 1.728 combinaciones de situación, detonante y desenlace; evita repetir premisas recientes. |
| Canales independientes | Implementada | Canales en SQLite, configuración e historial por canal; sin límite comercial de canales impuesto por Laburito. |
| Autopiloto que descubre temas | Parcial | Reglas activas eligen temas nuevos por nicho, evitan repetición y consultan Wikipedia, OpenAlex y señales de Google Trends; las fábricas de ficción generan episodios únicos. El modo rápido concentra la configuración en una sola pantalla, en lugar de un wizard de varias pantallas. La producción y entrega local se automatizan; YouTube nunca se autopublica. La prueba E2E `scripts/e2e_autopilot.py` cubre la ruta programada con Frutinovela. |
| Scheduler/worker persistente | Parcial | Worker SQLite, tick cada minuto, reintentos y recuperación de tareas interrumpidas. `scripts/e2e_autopilot.py` fuerza una regla vencida, produce y entrega un MP4 local, crea el siguiente episodio y simula recuperación de una tarea tras cierre abrupto. Local: requiere PC/proceso activo. Cloud: el workflow detecta que falta `LABURITO_URL`; `wake-app` y `deployment-smoke` se omiten. El almacenamiento cloud persistente no se pudo verificar. |
| Voces en español e inglés | Parcial | espeak-ng local ofrece voces en ambos idiomas; Piper aporta una voz neural española opcional. La locución puede usar voces inglesas y, si Ollama/Qwen local está disponible, los guiones automáticos se traducen al inglés conservando escenas. Sin Ollama se informa la limitación; los guiones propios se respetan. No se afirma paridad con catálogos comerciales ni clonación. |
| Clonación de voz | Ausente | No se integra un servicio pago de clonación. |
| Imágenes generadas por IA por escena | Ausente | Hay búsqueda de medios con licencias y recursos locales/procedurales; no hay un modelo generativo de imágenes integrado que cumpla paridad. |
| Video generado por IA / image-to-video | Ausente | No se integra el motor comercial de video IA. |
| Stock video y clips de fondo | Parcial | Búsqueda de recursos abiertos y uso de clips propios/autorizados; no hay catálogo comercial equivalente. |
| Avatares/talking head/UGC | Ausente | No hay motor de avatar humano realista. |
| Skeleton/talking objects | Parcial | Hay soporte de plantillas y render procedural para skeleton; no equivale a todos los motores visuales comerciales ni talking objects generativos. |
| Música de fondo y ducking | Implementada | Camas musicales locales, pistas propias y mezcla FFmpeg; un compresor sidechain reduce automáticamente la música cuando entra la narración. Catálogo menor que el comercial. |
| Subtítulos sincronizados | Parcial | Por defecto usa bloques rápidos con tiempos proporcionales. La opción avanzada puede usar Whisper.cpp tiny local para obtener marcas temporales por palabra en español/inglés; el estilo Karaoke muestra una palabra por cue. No se promete precisión perfecta al milisegundo ni resaltado progresivo de toda la frase. |
| Edición de escenas y regeneración parcial | Implementada | Editor, línea de tiempo, edición y regeneración individual de escenas/visuales. |
| Transiciones y overlays | Implementada | Transiciones, overlays de texto, voz, música y efectos. |
| Miniaturas y metadatos | Parcial | Miniaturas y metadatos locales; faltan capacidades de optimización/variantes y evaluación comparables. AITuber crea miniaturas por defecto en Autopilot y genera títulos/descripciones/tags por plataforma cuando publica. |
| Exportación 4K | Parcial | Render local configurable, 720p como valor CPU-friendly; no se ha verificado un pipeline 4K fiable en el hardware objetivo. |
| Biblioteca y cola de tareas | Implementada | Biblioteca local, cola SQLite, progreso, logs, reintentos y recuperación. El MP4 queda renderizado y disponible localmente sin exigir exportación manual. |
| Publicación multired a seis plataformas | Ausente | Integración existente enfocada en YouTube. YouTube requiere aprobación manual por cada video por decisión del usuario. |
| Analítica | Parcial | Importación de CSV de YouTube Studio y resumen; no hay conexiones nativas completas a seis plataformas. |
| Calendario y planificación | Parcial | Reglas con horario, frecuencia, próxima ejecución y cola; falta una vista calendario editorial más completa. |
| Variantes y reutilización | Parcial | Se puede duplicar/editar proyectos y regenerar escenas; falta el sistema comercial completo de variantes, recortes y reutilización multiplataforma. |
| API pública | Parcial | API REST propia para las funciones actuales, incluida creación por orden natural. No equivale a cobertura completa de la API comercial. |
| MCP | Ausente | No se identificó servidor MCP propio. |
| Colaboración/equipos | Ausente | No hay gestión multiusuario de equipos. |

## Diferencia económica y técnica

AITuber ofrece 100 créditos iniciales para el primer video y 25 para el primer Autopilot; el Autopilot continuo requiere un plan activo y los planes publicados empiezan en USD 39/mes. Sus páginas anuncian 1.300+ voces en 140+ idiomas, más de 27 estilos, imágenes y clips de video IA, stock footage, avatares, subtítulos sincronizados, música, regeneración por escena, 4K, API/MCP y publicación en seis redes. El centro de ayuda describe un wizard de Autopilot de aproximadamente dos minutos, con una pregunta por pantalla; también permite guardar videos en biblioteca sin conectar cuentas. La generación y publicación consume créditos.

Laburito prioriza una alternativa local y gratuita: FFmpeg, espeak-ng, Piper, SQLite, búsquedas de recursos abiertos y modelos locales opcionales. Eso evita créditos comerciales obligatorios, pero **no convierte automáticamente esas alternativas en equivalentes en calidad, variedad, velocidad o resolución**.

Referencias públicas consultadas:
- https://aituber.app/
- https://aituber.app/features/
- https://aituber.app/pricing/
- https://help.aituber.app/en/article/how-to-set-up-autopilot-a1d716/
- https://help.aituber.app/en/article/how-long-can-my-videos-be-1axgwnu/

## Próximas brechas prioritarias

1. Mantener las pruebas E2E de orden natural, piloto programado y entrega local; extender el piloto E2E a investigación de temas no ficticios con fuentes externas.
2. Desbloquear el scheduler cloud con URL real y almacenamiento persistente, sin sustituir la ejecución local gratuita.
3. Mejorar el selector de temas y la continuidad de canales/series, con prevención de duplicados probada.
4. Probar sincronía palabra por palabra y documentar exactamente el alcance.
5. Evaluar alternativas open source para imágenes/avatares sin exigir GPU dedicada ni servicios pagos.
6. Seguir simplificando el flujo móvil: revisión y regeneración de segmentos con acciones directas, menos pantallas y valores por defecto inteligentes.
7. Mantener bloqueada la publicación externa automática; cada video debe aprobarse individualmente.

No declarar paridad total hasta cerrar las brechas o documentar explícitamente por qué una capacidad comercial no tiene sustituto gratuito/local equivalente.


## Verificación técnica — 17/11/2026

| Capacidad / requisito | Estado | Evidencia en `appjet` |
|---|---|---|
| Orden natural sin esperar la investigación en la petición HTTP | **Implementada** | `POST /api/create-from-prompt` crea el proyecto y una tarea persistente `create_from_prompt`; el worker investiga, genera guion y renderiza bajo el mismo ID de tarea. |
| Progreso desde el inicio y reanudación sin regenerar el guion | **Implementada** | El worker registra etapa de investigación, guarda `script_ready` y las advertencias en `jobs.payload_json`, y reanuda el render usando ese estado. |
| Primera pantalla de creación rápida | **Implementada en interfaz** | El bloque de creación está antes del hero, con cuatro accesos directos y canal opcional; typecheck/build pasan. Falta prueba manual en un Android físico. |
| Piloto programado → MP4 → entrega local | **E2E añadido a CI** | `scripts/e2e_autopilot.py` ejecuta `autopilot.tick`, crea un episodio, reclama la cola, renderiza MP4 real, entrega a biblioteca local, programa un episodio distinto y simula recuperación tras reinicio. |
| Aprobación ligada al archivo exacto | **Implementada** | La migración SQLite añade `video_sha256`; los tests verifican rechazo de archivo modificado y reintentos solo para mismo job/MP4. |
| Canal automático por formato | **Parcial** | El selector prioriza canales del usuario compatibles con el formato y excluye las fábricas internas; si no hay canal compatible, el proyecto queda sin asignación. No hay clasificación semántica avanzada. |
| Aprobación por video para YouTube | **Implementada en backend** | La autorización se vincula a proyecto, tarea y SHA-256 del MP4 revisado. El worker vuelve a comprobar el hash inmediatamente antes de subir; si el archivo cambió, exige una aprobación nueva. Los reintentos solo valen para la misma tarea y el mismo archivo. |
| Bloqueo de tareas antiguas de autopublicación | **Implementada en interfaz, API y worker** | La creación/actualización de reglas rechaza `auto_publish=true` para YouTube; las reglas antiguas se normalizan a falso; `publish.set_auto_publish` y el scheduler bloquean YouTube; los jobs antiguos sin token fallan. La entrega local sí puede automatizarse. |
| Paridad audiovisual con AITuber | **Parcial** | La alternativa local usa FFmpeg, TTS local y material con licencia; no ofrece 1.300 voces, generación de imágenes/video IA comercial, clonación de voz ni 4K equivalente. |

La referencia pública de AITuber confirma voces 1.300+, estilos, IA visual, música, regeneración de escenas, exportación 4K, API/MCP, publicación en seis redes y Autopilot programado. Laburito prioriza creación inmediata, render y entrega local gratuitos con aprobación humana por video; la paridad del motor sigue siendo parcial por las restricciones de costo y hardware. No se afirma equivalencia de calidad, variedad ni velocidad.
