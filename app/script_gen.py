"""Guionista local: estructura narrativa sin APIs pagas.

Genera un andamiaje narrativo real (apertura, contexto, desarrollo, cierre) a
partir del tema del proyecto y de las notas de investigación cargadas por el
usuario. Es determinista y editable: cada escena puede regenerarse o reescribirse
a mano. Si existe un Ollama local accesible (gratuito y offline) se puede pedir
una expansión del texto; nunca se llama a servicios pagos.
"""
from __future__ import annotations

import hashlib
import json
import random
import urllib.error
import urllib.request

DOCUMENTARY_BLUEPRINT = [
    {
        "key": "apertura",
        "title": "Apertura cinematográfica",
        "weight": 0.08,
        "purpose": "Enganchar en los primeros segundos con una imagen sonora concreta y una pregunta.",
        "narration": (
            "Una guitarra limpia toca una frase simple. Después, un pie pisa un pedal y el sonido cambia para siempre. "
            "Lo que era una nota seca se convierte en una pared de sonido que sostiene canciones enteras. "
            "Detrás de ese pequeño interruptor hay circuitos, inventores, patentes y una industria que nadie planeó. "
            "Esta es la historia de {topic}, contada desde sus componentes hasta su legado. "
            "Y la pregunta que guía todo el recorrido es simple: ¿cómo algo tan pequeño cambió la forma de escuchar música?"
        ),
        "visual": "{topic} guitarra pedal primer plano",
    },
    {
        "key": "contexto",
        "title": "Contexto: por qué importa",
        "weight": 0.10,
        "purpose": "Explicar el punto de partida y por qué el tema merece 8 a 20 minutos.",
        "narration": (
            "Para entender {topic} hay que ubicarse en el momento exacto en que la tecnología y la música se cruzaron. "
            "Los músicos buscaban sonidos que no existían y las herramientas disponibles eran limitadas, caras y ruidosas. "
            "Ese deseo de algo nuevo es el motor de toda la historia: cuando la técnica no alcanza, aparece la improvisación, "
            "y cuando la improvisación funciona, aparece la industria. "
            "Antes de avanzar conviene ordenar el terreno: qué existía antes, quién lo usaba y por qué el resultado no conformaba a nadie."
        ),
        "visual": "{topic} historia contexto estudio grabación vintage",
    },
    {
        "key": "origen",
        "title": "El origen del efecto",
        "weight": 0.12,
        "purpose": "Mostrar los primeros experimentos, con nombres y fechas cuando estén verificados.",
        "narration": (
            "Todo empieza con un experimento que casi nadie registró. En talleres y garajes, técnicos y músicos tocaban cables, "
            "válvulas y parlantes para descubrir qué pasaba si se forzaba el circuito. "
            "La historia de {topic} no es la historia de un genio solitario: es la suma de pruebas, errores y copias que circulaban "
            "de mano en mano entre bandas y reparadores. "
            "Cada intento fallido dejaba una pista: un zumbido, una saturación, una oscilación que alguien decidió conservar porque sonaba bien."
        ),
        "visual": "{topic} taller válvulas circuito antiguo",
    },
    {
        "key": "protagonistas",
        "title": "Inventores y fabricantes",
        "weight": 0.12,
        "purpose": "Presentar a las personas y empresas, separando lo documentado de la leyenda.",
        "narration": (
            "Detrás de {topic} hay personas concretas: el técnico que ajustó el primer prototipo, el músico que lo usó en una grabación "
            "que se volvió famosa y el fabricante que decidió producirlo en serie. "
            "Las leyendas del origen suelen ser más ordenadas que los hechos: muchas veces el invento apareció en varios lugares a la vez "
            "y el crédito quedó para quien lo patentó o lo supo vender. "
            "Vale la pena distinguir tres cosas: lo que está documentado, lo que repiten las entrevistas y lo que la evidencia sugiere."
        ),
        "visual": "{topic} fabricante patente catálogo histórico",
    },
    {
        "key": "descubrimiento",
        "title": "El punto de inflexión",
        "weight": 0.12,
        "purpose": "Mostrar el momento en que el invento deja de ser curiosidad y se vuelve estándar.",
        "narration": (
            "Hay un momento en que {topic} deja de ser una rareza de taller y entra en las grabaciones que todo el mundo escucha. "
            "Un disco, una gira o un programa de televisión alcanzan para instalar un sonido en el oído colectivo. "
            "A partir de ahí la demanda cambia: los músicos lo piden, los fabricantes lo copian y el precio baja. "
            "La innovación técnica se convierte en lenguaje estético, y el lenguaje empieza a tener reglas propias."
        ),
        "visual": "{topic} escenario concierto años grabación",
    },
    {
        "key": "evolucion",
        "title": "Evolución técnica",
        "weight": 0.13,
        "purpose": "Explicar cómo cambió el circuito, el componente y el uso a lo largo del tiempo.",
        "narration": (
            "Con el paso de los años {topic} se volvió más barato, más pequeño y más confiable, pero también más estandarizado. "
            "Los componentes cambiaron de tecnología, las tolerancias se ajustaron y aparecieron versiones que intentaban reproducir "
            "el sonido de las primeras unidades, ya imposibles de encontrar. "
            "Cada generación resolvió un problema y creó otro: menos ruido, menos carácter; más control, menos sorpresa. "
            "Esa tensión entre precisión y personalidad explica buena parte de las discusiones actuales."
        ),
        "visual": "{topic} diagrama circuito componentes evolución",
    },
    {
        "key": "consecuencias",
        "title": "Impacto cultural",
        "weight": 0.13,
        "purpose": "Conectar el objeto con la música, la economía y la cultura.",
        "narration": (
            "El impacto de {topic} se mide en discos, pero también en oficios: aparecieron reparadores, coleccionistas, "
            "fabricantes pequeños y comunidades enteras dedicadas a comparar versiones y documentar diferencias. "
            "La cultura material creció alrededor del sonido: catálogos, manuales, foros y grabaciones de demostración. "
            "Nada de esto fue planificado por una sola empresa; fue el resultado de miles de decisiones pequeñas tomadas por músicos y técnicos."
        ),
        "visual": "{topic} colección catálogo comunidad taller",
    },
    {
        "key": "legado",
        "title": "Legado y consecuencias abiertas",
        "weight": 0.11,
        "purpose": "Cerrar el arco principal mostrando qué queda hoy.",
        "narration": (
            "Hoy {topic} sigue presente, aunque ya no ocupe el centro de la conversación. "
            "Queda en las grabaciones, en los circuitos que se copian y en la forma en que los músicos piensan el sonido. "
            "Su historia deja una lección sobre la innovación: casi nunca ocurre en un laboratorio ordenado, "
            "sino en manos de gente que prueba cosas sin permiso y encuentra algo que valía la pena conservar."
        ),
        "visual": "{topic} actualidad estudio grabación moderna",
    },
    {
        "key": "cierre",
        "title": "Cierre",
        "weight": 0.09,
        "purpose": "Sintetizar y abrir conversación sin prometer conclusiones que no se sostienen.",
        "narration": (
            "Si algo muestra la historia de {topic} es que el sonido que hoy parece inevitable fue, en su momento, una decisión discutible. "
            "Alguien eligió conservar un defecto porque sonaba mejor que la limpieza. "
            "Queda una pregunta abierta: ¿cuántos sonidos que hoy descartamos van a definir la música de las próximas décadas? "
            "Si te interesa este tipo de historias, contanos en los comentarios qué otro invento musical querés ver investigado."
        ),
        "visual": "{topic} cierre estudio mezcla consola",
    },
]

SHORT_BLUEPRINT = [
    {
        "key": "hook",
        "title": "Hook (0-3 s)",
        "weight": 0.16,
        "purpose": "Detener el scroll con una afirmación concreta y verificable.",
        "narration": (
            "Un pedal de guitarra puede costar menos que una pizza y cambiar por completo una canción. "
            "Te muestro cómo {topic} pasó de un experimento de taller a un sonido que reconocés en dos segundos."
        ),
        "visual": "{topic} pedal primer plano vertical",
    },
    {
        "key": "idea",
        "title": "Idea central",
        "weight": 0.26,
        "purpose": "Una sola idea, explicada sin rodeos.",
        "narration": (
            "La clave de {topic} no es la tecnología: es el error controlado. "
            "Al forzar el circuito aparece una distorsión que los músicos decidieron no corregir. "
            "Lo que la ingeniería llamaba falla, la música lo llamó estilo."
        ),
        "visual": "{topic} circuito distorsión",
    },
    {
        "key": "desarrollo",
        "title": "Desarrollo breve",
        "weight": 0.28,
        "purpose": "Dos o tres datos concretos que sostienen la idea.",
        "narration": (
            "Los primeros modelos se armaban a mano, con componentes que cambiaban según lo que hubiera disponible. "
            "Por eso dos unidades iguales sonaban distinto. "
            "Cuando la producción se estandarizó, el sonido se volvió previsible y empezó la búsqueda de las versiones originales. "
            "Hoy un coleccionista paga más por una unidad vieja que por un modelo nuevo, y no es solo por moda."
        ),
        "visual": "{topic} componentes manual taller",
    },
    {
        "key": "giro",
        "title": "Giro",
        "weight": 0.15,
        "purpose": "Aportar el dato que reordena la historia.",
        "narration": (
            "El giro es este: el invento más famoso de {topic} muchas veces no fue el primero, sino el que se fabricó más rápido. "
            "La historia del sonido también se escribe con logística."
        ),
        "visual": "{topic} fabricación serie caja",
    },
    {
        "key": "cierre",
        "title": "Cierre",
        "weight": 0.15,
        "purpose": "Invitar a comentar o compartir con una pregunta concreta.",
        "narration": (
            "Guardá este video si te gusta la historia de la música. "
            "¿Cuál es el sonido que reconocerías en dos segundos? Te leo en los comentarios."
        ),
        "visual": "{topic} guitarra cierre",
    },
]


def _hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]


def blueprint(kind: str) -> list[dict]:
    return DOCUMENTARY_BLUEPRINT if kind == "documentary" else SHORT_BLUEPRINT


def _claims(notes: list[dict]) -> list[str]:
    out = []
    for note in notes:
        claim = (note.get("claim") or "").strip()
        if claim:
            out.append(claim)
    return out


def _attribution(note: dict) -> str:
    url = note.get("source_url") or ""
    level = {"hecho": "dato comprobado", "indicio": "indicio", "estimacion": "estimación"}.get(
        note.get("evidence_level", "indicio"), "indicio"
    )
    if url:
        return f" ({level}; fuente: {url})"
    return f" ({level})"


def generate_script(
    project: dict,
    notes: list[dict] | None = None,
    sources: list[dict] | None = None,
) -> dict:
    """Devuelve escenas con narración, intención y búsqueda visual."""
    notes = notes or []
    sources = sources or []
    topic = (project.get("topic") or project.get("title") or "el tema").strip()
    kind = project.get("kind") or "documentary"
    target = int(project.get("duration_target_sec") or (600 if kind == "documentary" else 40))
    beats = blueprint(kind)

    claims = _claims(notes)
    rnd = random.Random(_hash(f"{project.get('id')}-{topic}-{kind}"))
    rnd.shuffle(claims)

    scenes = []
    claim_index = 0
    for idx, beat in enumerate(beats):
        narration = beat["narration"].format(topic=topic)
        # Inyecta evidencia real del usuario en los beats de desarrollo.
        if beat["key"] in ("origen", "protagonistas", "descubrimiento", "evolucion", "consecuencias", "desarrollo"):
            if claim_index < len(claims):
                note = None
                for candidate in notes:
                    if (candidate.get("claim") or "").strip() == claims[claim_index]:
                        note = candidate
                        break
                if note:
                    narration += f" Un dato para sostenerlo: {claims[claim_index].rstrip('.')}{_attribution(note)}."
                    claim_index += 1
        duration = max(3.0, round(target * beat["weight"], 2))
        scenes.append(
            {
                "idx": idx,
                "title": beat["title"],
                "beat": beat["key"],
                "purpose": beat["purpose"],
                "narration": narration,
                "visual_query": beat["visual"].format(topic=topic),
                "duration_target_sec": duration,
                "transition": "fundido" if beat["key"] in ("apertura", "cierre") else "corte",
                "status": "borrador",
            }
        )

    unused = [n for n in notes if (n.get("claim") or "").strip() not in claims[:claim_index]]
    return {
        "title": project.get("title") or f"Documental: {topic}",
        "kind": kind,
        "topic": topic,
        "scenes": scenes,
        "warnings": [
            "Borrador generado con plantillas narrativas locales: requiere revisión humana antes de publicar.",
        ]
        + ([f"{len(unused)} nota(s) de investigación sin usar; revisalas y sumalas como escenas."] if unused else []),
        "sources_considered": len(sources),
        "notes_used": claim_index,
    }


_VARIANTS = [
    ("Entremos por el detalle", "En lugar de empezar por el contexto, arranquemos por el objeto."),
    ("Entremos por el conflicto", "El relato gana tensión cuando mostramos quién se oponía al cambio."),
    ("Entremos por la pregunta", "Abrir con una pregunta concreta sostiene mejor la atención."),
]


def regenerate_scene(scene: dict, project: dict, variant: int = 0) -> dict:
    """Reformula una escena manteniendo el sentido (regeneración parcial)."""
    topic = (project.get("topic") or project.get("title") or "el tema").strip()
    text = (scene.get("narration") or "").strip()
    style, hint = _VARIANTS[variant % len(_VARIANTS)]
    lead = {
        0: f"Vamos al detalle. {topic} no cambia por lo que dice un manual, sino por lo que pasa en el momento exacto en que alguien lo usa.",
        1: f"Acá hay un conflicto. La historia de {topic} avanzó porque alguien insistió cuando el resto decía que no servía.",
        2: f"Una pregunta antes de seguir: ¿qué tendría que pasar para que {topic} sonara distinto a todo lo anterior?",
    }[variant % 3]
    body = text or f"La escena sobre {topic} todavía no tiene narración escrita."
    narration = f"{lead} {body}"
    return {
        "narration": narration,
        "status": "borrador",
        "note": f"Variante «{style}»: {hint}",
    }


def ollama_available(url: str) -> bool:
    if not url:
        return False
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/api/tags", timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False


def expand_with_ollama(url: str, model: str, prompt: str, timeout: int = 120) -> str:
    """Expansión opcional con un modelo local (Ollama). Cero coste, sin claves."""
    if not ollama_available(url):
        raise RuntimeError(
            "Ollama no está accesible. Es opcional: instalalo desde ollama.com y configurá la URL "
            "en Configuración para expandir guiones con un modelo local."
        )
    payload = json.dumps({"model": model or "llama3.2", "prompt": prompt, "stream": False}).encode()
    req = urllib.request.Request(
        url.rstrip("/") + "/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return (data.get("response") or "").strip()
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Ollama no respondió: {exc}") from exc
