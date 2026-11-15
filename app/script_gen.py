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
import re
import urllib.error
import urllib.request

from . import options

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
        "purpose": "Abrir con el dato, pregunta o contradicción más sorprendente que esté respaldada por las fuentes.",
        "narration": "Hay un detalle de {topic} que cambia cómo se entiende el tema. En este short vamos directo a lo importante.",
        "visual": "{topic} imagen principal vertical primer plano",
    },
    {
        "key": "contexto",
        "title": "Contexto mínimo",
        "weight": 0.16,
        "purpose": "Dar solo el contexto imprescindible para comprender el dato inicial.",
        "narration": "Para entenderlo, primero hay que ubicar qué pasó y por qué importa.",
        "visual": "{topic} contexto visual vertical",
    },
    {
        "key": "desarrollo",
        "title": "Desarrollo",
        "weight": 0.30,
        "purpose": "Explicar el mecanismo, los hechos o la secuencia con información concreta y atribuible.",
        "narration": "La clave está en los hechos: qué ocurrió, qué lo explica y qué evidencia tenemos.",
        "visual": "{topic} detalle evidencia explicación vertical",
    },
    {
        "key": "giro",
        "title": "Dato que cambia la perspectiva",
        "weight": 0.20,
        "purpose": "Revelar el dato más inesperado disponible, sin exagerar ni inventar un giro.",
        "narration": "Y hay un dato más que cambia la perspectiva sobre {topic}.",
        "visual": "{topic} detalle inesperado comparación vertical",
    },
    {
        "key": "cierre",
        "title": "Cierre y conversación",
        "weight": 0.18,
        "purpose": "Cerrar con una conclusión breve y una pregunta específica que invite a comentar.",
        "narration": "Esa es la parte importante de {topic}. ¿Qué aspecto te gustaría que investiguemos después?",
        "visual": "{topic} conclusión visual vertical",
    },
]


LISTICLE_BLUEPRINT = [
    {
        "key": "hook",
        "title": "Hook + promesa de la lista",
        "weight": 0.14,
        "purpose": "Prometer un valor concreto y enumerable en los primeros segundos.",
        "narration": (
            "Hay {topic} que casi nadie mira dos veces y que cambian todo cuando los entendés. "
            "Te dejo los puntos clave, del más obvio al que menos se comenta."
        ),
        "visual": "{topic} collage primer plano vertical",
    },
    {
        "key": "punto_1",
        "title": "Punto 1",
        "weight": 0.17,
        "purpose": "Primer punto: claro, comprobable y con un ejemplo.",
        "narration": (
            "Punto uno: lo básico de {topic} no es lo que se dice en los titulares. "
            "El detalle que importa es más chico y más concreto de lo que parece."
        ),
        "visual": "{topic} detalle uno",
    },
    {
        "key": "punto_2",
        "title": "Punto 2",
        "weight": 0.17,
        "purpose": "Segundo punto: agrega una capa nueva, no repite.",
        "narration": (
            "Punto dos: acá aparece la parte que cambia la ecuación. "
            "Cuando se mira de cerca, {topic} deja de ser una anécdota y se vuelve un patrón."
        ),
        "visual": "{topic} comparación lado a lado",
    },
    {
        "key": "desarrollo",
        "title": "Punto 3 (el menos conocido)",
        "weight": 0.20,
        "purpose": "Tercer punto: el dato que justifica el vídeo.",
        "narration": (
            "Punto tres, el que casi nadie menciona: {topic} también tiene un costo que no se ve. "
            "Y ese costo explica por qué el resto de la lista funciona así."
        ),
        "visual": "{topic} gráfico datos",
    },
    {
        "key": "punto_4",
        "title": "Punto 4 / mención rápida",
        "weight": 0.15,
        "purpose": "Cerrar la enumeración con ritmo rápido.",
        "narration": (
            "Y para cerrar la lista: si tuvieras que quedarte con una sola idea de {topic}, "
            "quedate con esta. El resto se aprende mirando de nuevo."
        ),
        "visual": "{topic} resumen mosaico",
    },
    {
        "key": "cta",
        "title": "Cierre y llamada",
        "weight": 0.17,
        "purpose": "Cerrar sin prometer de más e invitar a seguir.",
        "narration": (
            "Guardá este vídeo si te sirvió y decime cuál de los puntos te sorprendió más. "
            "En el próximo seguimos con {topic} desde otro ángulo."
        ),
        "visual": "{topic} cierre pantalla final",
    },
]

POV_BLUEPRINT = [
    {
        "key": "hook",
        "title": "Hook en segunda persona",
        "weight": 0.15,
        "purpose": "Meter al espectador en la escena de inmediato.",
        "narration": (
            "Imaginate que estás ahí, a un paso de entender {topic}, y nadie te avisó lo que venía. "
            "Todo empieza con un detalle mínimo."
        ),
        "visual": "{topic} escena inmersiva primer plano",
    },
    {
        "key": "contexto",
        "title": "El contexto que no se ve",
        "weight": 0.20,
        "purpose": "Dar el marco mínimo para que la escena tenga peso.",
        "narration": (
            "Lo que nadie te cuenta es el contexto: {topic} no pasó de golpe. "
            "Fue una suma de decisiones chicas que, juntas, ya no tenían vuelta atrás."
        ),
        "visual": "{topic} contexto ambiente",
    },
    {
        "key": "desarrollo",
        "title": "El giro",
        "weight": 0.28,
        "purpose": "El cambio de información que reencuadra todo lo anterior.",
        "narration": (
            "Y acá viene el giro: lo que parecía un problema de {topic} era, en realidad, el síntoma. "
            "Cuando lo ves así, la historia cambia de protagonista."
        ),
        "visual": "{topic} giro dramático",
    },
    {
        "key": "consecuencias",
        "title": "La consecuencia",
        "weight": 0.20,
        "purpose": "Mostrar qué se pierde o se gana con ese giro.",
        "narration": (
            "La consecuencia es simple y difícil de aceptar: con {topic} no se puede volver atrás. "
            "Solo se puede elegir qué hacer con lo que queda."
        ),
        "visual": "{topic} consecuencia después",
    },
    {
        "key": "cierre",
        "title": "Cierre reflexivo",
        "weight": 0.17,
        "purpose": "Cerrar con una pregunta abierta y honesta.",
        "narration": (
            "Si estuvieras en esa situación, ¿qué habrías hecho distinto? "
            "Contame abajo: las mejores respuestas las leo todas."
        ),
        "visual": "{topic} cierre silencio",
    },
]

EXPLAINER_BLUEPRINT = [
    {
        "key": "apertura",
        "title": "La pregunta",
        "weight": 0.10,
        "purpose": "Formular la pregunta que el vídeo responde.",
        "narration": (
            "¿Cómo funciona {topic}, exactamente? No la versión de manual: la que se entiende "
            "cuando alguien te lo explica sin apuro."
        ),
        "visual": "{topic} pregunta pizarra",
    },
    {
        "key": "contexto",
        "title": "De dónde viene",
        "weight": 0.18,
        "purpose": "Origen y marco mínimo necesario.",
        "narration": (
            "Primero, de dónde viene {topic}. Sin este punto de partida, el resto parece magia "
            "y no lo es: es una cadena de pasos que se puede seguir."
        ),
        "visual": "{topic} línea de tiempo origen",
    },
    {
        "key": "desarrollo",
        "title": "Paso 1: el mecanismo",
        "weight": 0.24,
        "purpose": "Explicar el mecanismo central en un solo paso.",
        "narration": (
            "Paso uno, el mecanismo: {topic} funciona porque separa lo que entra de lo que sale. "
            "Esa separación es toda la idea, el resto son detalles de implementación."
        ),
        "visual": "{topic} diagrama mecanismo",
    },
    {
        "key": "protagonistas",
        "title": "Paso 2: quién lo hace posible",
        "weight": 0.22,
        "purpose": "Mostrar los actores y sus incentivos.",
        "narration": (
            "Paso dos, los actores: detrás de {topic} hay gente con incentivos distintos. "
            "Cuando esos incentivos se alinean, el sistema avanza; cuando chocan, se traba."
        ),
        "visual": "{topic} actores reunión",
    },
    {
        "key": "consecuencias",
        "title": "Paso 3: qué implica",
        "weight": 0.16,
        "purpose": "Consecuencias prácticas y límites.",
        "narration": (
            "Paso tres, las implicancias: entender {topic} cambia qué decisiones tomás. "
            "Y también cambia qué promesas conviene no creer."
        ),
        "visual": "{topic} aplicación práctica",
    },
    {
        "key": "cierre",
        "title": "Resumen en 20 segundos",
        "weight": 0.10,
        "purpose": "Recapitular y dejar un cierre claro.",
        "narration": (
            "Resumen: {topic} es una cadena de pasos, no un misterio. "
            "Si te quedó una duda, dejala en los comentarios y la resolvemos en el próximo vídeo."
        ),
        "visual": "{topic} resumen final",
    },
]

QUOTE_BLUEPRINT = [
    {
        "key": "hook",
        "title": "La frase",
        "weight": 0.22,
        "purpose": "Presentar la cita de forma directa y visual.",
        "narration": (
            "Hay una frase sobre {topic} que se repite mucho y se entiende poco. "
            "Vale la pena mirarla de cerca."
        ),
        "visual": "{topic} cita tipografía vertical",
    },
    {
        "key": "contexto",
        "title": "Quién la dijo y cuándo",
        "weight": 0.22,
        "purpose": "Dar autoría y contexto real, sin inventar atribuciones.",
        "narration": (
            "El contexto importa: la frase sobre {topic} nace en un momento concreto, "
            "con intereses concretos. Sin eso, es solo una frase linda."
        ),
        "visual": "{topic} retrato archivo",
    },
    {
        "key": "desarrollo",
        "title": "Qué significa de verdad",
        "weight": 0.28,
        "purpose": "Traducir la cita a una idea aplicable.",
        "narration": (
            "Traducida a la práctica, la frase dice algo simple sobre {topic}: "
            "lo que se mide cambia lo que se hace, y lo que no se mide se olvida."
        ),
        "visual": "{topic} detalle simbólico",
    },
    {
        "key": "cierre",
        "title": "Cierre",
        "weight": 0.28,
        "purpose": "Cerrar con la idea y una pregunta.",
        "narration": (
            "Si te sirvió, guardala. Y si conocés otra frase sobre {topic} que diga lo contrario, "
            "traéla: las contradicciones son la parte interesante."
        ),
        "visual": "{topic} cierre cielo",
    },
]

BLUEPRINTS = {
    "documentary": DOCUMENTARY_BLUEPRINT,
    "short": SHORT_BLUEPRINT,
    "listicle": LISTICLE_BLUEPRINT,
    "pov": POV_BLUEPRINT,
    "explainer": EXPLAINER_BLUEPRINT,
    "quote": QUOTE_BLUEPRINT,
}

def _hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]


def blueprint(kind: str) -> list[dict]:
    """Blueprint narrativo por plantilla de guion (6 plantillas)."""
    return BLUEPRINTS.get(kind or "", DOCUMENTARY_BLUEPRINT)


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
    kind = project.get("kind") or "short"
    tpl = options.template(project.get("template"))
    script_kind = tpl.get("script") or kind
    target = int(
        project.get("duration_target_sec")
        or tpl.get("default_duration")
        or (30 if kind == "short" else 600)
    )
    beats = blueprint(script_kind)

    source_notes = [
        note for note in notes
        if note.get("source_url") and len((note.get("claim") or "")) >= 450
    ]
    source_note = source_notes[0] if source_notes else None
    evidence_sentences: list[str] = []
    if source_notes:
        raw = " ".join(
            re.sub(r"\[[0-9]+\]", "", note.get("claim") or "")
            for note in source_notes[:5]
        )
        evidence_sentences = [
            re.sub(r"\s+", " ", sentence).strip()
            for sentence in re.split(r"(?<=[.!?])\s+", raw)
            if len(sentence.strip()) >= 45
        ]

    # Never fill an automatic script with generic facts unrelated to the topic.
    # If the source has fewer facts than the template, reduce the scene count.
    if evidence_sentences:
        beats = beats[:min(len(beats), len(evidence_sentences))]
        evidence_sentences = evidence_sentences[:max(len(beats), int(target / 10))]

    claims = _claims([n for n in notes if n is not source_note])
    rnd = random.Random(_hash(f"{project.get('id')}-{topic}-{kind}"))
    rnd.shuffle(claims)

    scenes = []
    claim_index = 0
    for idx, beat in enumerate(beats):
        narration = beat["narration"].format(topic=topic)
        if evidence_sentences:
            first = idx * len(evidence_sentences) // len(beats)
            last = (idx + 1) * len(evidence_sentences) // len(beats)
            factual = evidence_sentences[first:last]
            narration = (f"Sobre {topic}: " if idx == 0 else "") + " ".join(factual)
        elif beat["key"] in ("origen", "protagonistas", "descubrimiento", "evolucion", "consecuencias", "desarrollo"):
            if claim_index < len(claims):
                note = next((n for n in notes if (n.get("claim") or "").strip() == claims[claim_index]), None)
                if note:
                    narration += f" Dato de contexto: {claims[claim_index].rstrip('.')}{_attribution(note)}."
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

    unused = [n for n in notes if n is not source_note and (n.get("claim") or "").strip() not in claims[:claim_index]]
    return {
        "title": project.get("title") or f"Short: {topic}",
        "kind": kind,
        "topic": topic,
        "scenes": scenes,
        "warnings": [
            "Guion estructurado con extractos de una fuente de orientación; contrastar datos con fuentes independientes antes de publicar." if source_note and evidence_sentences else "Borrador de plantilla local sin evidencia suficiente: no publicar automáticamente.",
        ]
        + ([f"{len(unused)} nota(s) de investigación sin usar; revisalas y sumalas como escenas."] if unused else []),
        "sources_considered": len(sources),
        "notes_used": len(source_notes) if source_notes and evidence_sentences else claim_index,
        "evidence_sources": len(source_notes),
        "writer": "source-extract" if source_note and evidence_sentences else "template",
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



def rewrite_with_ollama(url: str, model: str, project: dict, script: dict, notes: list[dict]) -> dict:
    """Reescribe el guion con un modelo Ollama local, usando solo la evidencia recuperada."""
    source_notes = [
        note for note in notes
        if note.get("source_url") and len((note.get("claim") or "")) >= 300
    ][:5]
    if not source_notes:
        raise RuntimeError("No hay fuentes documentales suficientes para redactar el guion.")
    scenes = script.get("scenes") or []
    outline = [
        {
            "idx": scene.get("idx"),
            "title": scene.get("title"),
            "duration_target_sec": scene.get("duration_target_sec"),
        }
        for scene in scenes
    ]
    prompt = (
        "Escribí un guion audiovisual original en español para un canal de YouTube. "
        "Usá exclusivamente los datos del material de referencia: no inventes personas, fechas, cifras, "
        "causas ni citas. Parafraseá; no copies párrafos. Si falta información, omitila. "
        "La primera escena debe enganchar, las siguientes deben desarrollar una progresión clara y el cierre "
        "debe dejar una idea o pregunta concreta. Evitá relleno, repeticiones y frases genéricas. "
        "Respetá exactamente la cantidad y el orden de escenas del esquema. "
        "Devolvé únicamente JSON válido con esta forma: {\"scenes\":[{\"idx\":0,\"narration\":\"...\"}]}.\n\n"
        f"Tema: {project.get('topic') or project.get('title')}\n"
        f"Duración total objetivo: {project.get('duration_target_sec')} segundos\n"
        f"Esquema: {json.dumps(outline, ensure_ascii=False)}\n"
        "Material de referencia (cada bloque incluye su fuente; contrastá coincidencias y discrepancias):\n"
        + "\n\n".join(
            f"FUENTE: {note.get('source_url', '')}\nCONTENIDO: {(note.get('claim') or '')[:5000]}"
            for note in source_notes
        )
    )
    raw = expand_with_ollama(url, model, prompt, timeout=240)
    cleaned = raw.strip()
    if cleaned.startswith(chr(96) * 3):
        cleaned = re.sub(r"^\x60{3}(?:json)?\s*|\s*\x60{3}$", "", cleaned, flags=re.IGNORECASE)
    first = cleaned.find("{")
    last = cleaned.rfind("}")
    if first < 0 or last <= first:
        raise RuntimeError("Ollama no devolvió un JSON reconocible.")
    data = json.loads(cleaned[first:last + 1])
    generated = data.get("scenes") if isinstance(data, dict) else None
    if not isinstance(generated, list) or len(generated) != len(scenes):
        raise RuntimeError("Ollama devolvió una cantidad de escenas distinta a la solicitada.")
    by_idx = {int(item.get("idx", -1)): item for item in generated if isinstance(item, dict)}
    rewritten = []
    for scene in scenes:
        item = by_idx.get(int(scene.get("idx", -1)))
        narration = str((item or {}).get("narration") or "").strip()
        if len(narration) < 35:
            raise RuntimeError(f"Ollama dejó vacía o demasiado corta la escena {scene.get('idx')}.")
        rewritten.append({**scene, "narration": narration})
    return {
        **script,
        "scenes": rewritten,
        "warnings": [
            *script.get("warnings", []),
            "Guion reescrito con un modelo Ollama local; contrastá cada afirmación con las fuentes antes de publicar.",
        ],
        "writer": "ollama-local",
        "evidence_sources": len(source_notes),
    }
