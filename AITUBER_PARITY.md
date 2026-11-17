# Matriz de paridad funcional con AITuber.app

**Objetivo:** reproducir la experiencia y las capacidades útiles de AITuber.app sin copiar código, marca ni recursos propietarios, manteniendo costo obligatorio $0 y procesamiento local cuando sea viable.

**Fecha de auditoría:** 2026-11-16  
**Rama auditada:** `appjet`

Estados:
- **Implementada:** existe en Laburito y hay pruebas o código verificable.
- **Parcial:** existe una alternativa funcional, pero no alcanza la capacidad/experiencia completa de AITuber.
- **Ausente:** no existe una implementación utilizable identificada.
- **Bloqueada:** el código existe, pero falta una configuración externa para que funcione en el despliegue correspondiente.

## Matriz

| Capacidad de AITuber | Estado Laburito | Evidencia / diferencia |
|---|---|---|
| Crear un video desde una idea breve | Parcial | Flujo «Decilo y se hace» en Inicio, con accesos de un toque para Short, Historia, Frutinovela y Documental, selector de canal opcional y envío directo al editor/cola. Interpreta comandos comunes, crea proyecto, genera guion y encola render. Parser determinista; no es un agente conversacional multimodal. |
| Pegar un guion propio y convertirlo a video | Implementada | Endpoint de guion y pipeline de escenas existente. |
| Shorts verticales | Implementada | Plantillas verticales, subtítulos, voz, visuales y render FFmpeg. |
| Documentales largos | Parcial | Pipeline horizontal disponible, con duración limitada a 20 minutos; falta comparar calidad/variedad visual con el motor comercial. |
| Frutinovelas episódicas | Implementada | Plantilla propia, personajes recurrentes, continuidad y cliffhangers. |
| Historias estilo Reddit | Implementada | Fábrica interna y plantilla de ficción. |
| Canales independientes | Implementada | Canales en SQLite, configuración e historial por canal; sin límite comercial de canales impuesto por Laburito. |
| Autopiloto que descubre temas | Parcial | Reglas activas eligen temas nuevos por nicho, evitan repetición y consultan Wikipedia, OpenAlex y señales de Google Trends. La configuración rápida hereda el nicho del canal elegido para reducir pasos. La selección depende de un nicho configurado una vez; no publica automáticamente. |
| Scheduler/worker persistente | Parcial | Worker SQLite de un hilo, tick del autopiloto cada minuto, reintentos y recuperación de tareas interrumpidas. Local: requiere PC/proceso activo. Cloud: el workflow de wake-up requiere `LABURITO_URL` real y persistencia; esa URL todavía no está configurada. |
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
| Miniaturas y metadatos | Parcial | Miniaturas y metadatos locales; faltan capacidades de optimización/variantes y evaluación comparables. |
| Exportación 4K | Parcial | Render local configurable, 720p como valor CPU-friendly; no se ha verificado un pipeline 4K fiable en el hardware objetivo. |
| Biblioteca y cola de tareas | Implementada | Biblioteca local, cola SQLite, progreso, logs, reintentos y recuperación. |
| Publicación multired a seis plataformas | Ausente | Integración existente enfocada en YouTube. YouTube requiere aprobación manual por cada video por decisión del usuario. |
| Analítica | Parcial | Importación de CSV de YouTube Studio y resumen; no hay conexiones nativas completas a seis plataformas. |
| API pública | Parcial | API REST propia para las funciones actuales, incluida creación por orden natural. No equivale a cobertura completa de la API comercial. |
| MCP | Ausente | No se identificó servidor MCP propio. |
| Colaboración/equipos | Ausente | No hay gestión multiusuario de equipos. |

## Diferencia económica y técnica

AITuber anuncia planes pagos desde USD 39/mes, con créditos por generación; el propio sitio indica que las voces usan ElevenLabs y que la generación de imágenes/video consume créditos. Su página de funciones anuncia 1.300+ voces, estilos, imágenes/video IA, avatares, exportación 4K y publicación en varias redes.

Laburito prioriza una alternativa local y gratuita: FFmpeg, espeak-ng, Piper, SQLite, búsquedas de recursos abiertos y modelos locales opcionales. Eso evita créditos comerciales obligatorios, pero **no convierte automáticamente esas alternativas en equivalentes en calidad, variedad, velocidad o resolución**.

Referencias públicas consultadas:
- https://aituber.app/
- https://aituber.app/features/
- https://aituber.app/pricing/
- https://help.aituber.app/en/article/how-to-set-up-autopilot-a1d716/
- https://help.aituber.app/en/article/how-long-can-my-videos-be-1axgwnu/

## Próximas brechas prioritarias

1. Cerrar la prueba de extremo a extremo del flujo de orden natural con MP4 real y estado final correcto; la validación detectó y corrigió margen insuficiente de duración para historias.
2. Desbloquear el scheduler cloud con URL real y almacenamiento persistente, sin sustituir la ejecución local gratuita.
3. Mejorar el selector de temas y la continuidad de canales/series, con prevención de duplicados probada.
4. Probar sincronía palabra por palabra y documentar exactamente el alcance.
5. Evaluar alternativas open source para imágenes/avatares sin exigir GPU dedicada ni servicios pagos.
6. Seguir simplificando el flujo móvil: revisión y regeneración de segmentos con acciones directas, menos pantallas y valores por defecto inteligentes.
7. Mantener bloqueada la publicación externa automática; cada video debe aprobarse individualmente.

No declarar paridad total hasta cerrar las brechas o documentar explícitamente por qué una capacidad comercial no tiene sustituto gratuito/local equivalente.
