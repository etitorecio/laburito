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

def script_from_text(project: dict, raw_text: str) -> dict:
    """Convierte un guion escrito por el usuario en escenas listas para renderizar."""
    text = (raw_text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise ValueError("El guion está vacío.")
    if len(text) > 12000:
        raise ValueError("El guion no puede superar los 12.000 caracteres.")

    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    chunks: list[str] = []
    for paragraph in paragraphs:
        sentences = [part.strip() for part in re.split(r"(?<=[.!?…])\s+", paragraph) if part.strip()]
        if not sentences:
            sentences = [paragraph]
        current: list[str] = []
        words = 0
        for sentence in sentences:
            sentence_words = len(sentence.split())
            if current and words + sentence_words > 65:
                chunks.append(" ".join(current))
                current, words = [], 0
            if sentence_words > 65 and not current:
                tokens = sentence.split()
                for start in range(0, len(tokens), 65):
                    chunks.append(" ".join(tokens[start:start + 65]))
                continue
            current.append(sentence)
            words += sentence_words
        if current:
            chunks.append(" ".join(current))

    topic = str(project.get("topic") or project.get("title") or "video").strip()
    scenes = []
    for index, narration in enumerate(chunks):
        words = re.findall(r"\w+", narration, flags=re.UNICODE)
        title = " ".join(words[:7]).strip().capitalize() or f"Escena {index + 1}"
        scenes.append({
            "idx": index,
            "title": title[:72],
            "narration": narration,
            "visual_query": f"{topic} {title} escena ilustrativa",
            "transition": "fundido",
        })
    return {
        "scenes": scenes,
        "warnings": ["Guion propio: se respetó el texto proporcionado y se dividió en escenas para el render."],
        "writer": "user-script",
    }


DOCUMENTARY_BLUEPRINT = [
    {
        "key": "apertura",
        "title": "Apertura y pregunta central",
        "weight": 0.07,
        "purpose": "Abrir con una escena concreta y plantear la pregunta que el documental va a responder.",
        "narration": "Hay una pregunta que atraviesa toda la historia de {topic}: ¿cómo llegó a convertirse en algo relevante? Para responderla no alcanza con repetir la versión más conocida. Hay que volver al contexto, seguir las decisiones y distinguir los hechos comprobados de las explicaciones que aparecieron después.",
        "visual": "{topic} imagen documental de apertura",
    },
    {
        "key": "contexto",
        "title": "El contexto",
        "weight": 0.09,
        "purpose": "Ubicar época, lugar, condiciones y problema inicial.",
        "narration": "Antes de que {topic} tomara la forma que conocemos, existían condiciones concretas que hicieron posible su aparición. La época, los recursos disponibles y las necesidades de quienes participaron explican por qué ciertas decisiones tenían sentido entonces, aunque hoy parezcan evidentes o extrañas.",
        "visual": "{topic} contexto histórico lugar época",
    },
    {
        "key": "origen",
        "title": "Los primeros pasos",
        "weight": 0.11,
        "purpose": "Reconstruir los orígenes sin adjudicar inventos o fechas sin respaldo.",
        "narration": "El origen de {topic} no debe reducirse a una fecha aislada ni a un único protagonista si las fuentes muestran un proceso más amplio. Para reconstruirlo hay que seguir los primeros antecedentes, identificar qué está documentado y señalar qué partes siguen siendo discutidas o incompletas.",
        "visual": "{topic} documentos archivo primeros antecedentes",
    },
    {
        "key": "protagonistas",
        "title": "Personas e instituciones",
        "weight": 0.11,
        "purpose": "Presentar a los actores relevantes y explicar sus intereses y aportes.",
        "narration": "La historia también se construye a través de las personas, grupos e instituciones que tomaron decisiones. No todos perseguían el mismo objetivo: algunos buscaban resolver un problema, otros sostener una actividad y otros aprovechar una oportunidad. Entender esas diferencias permite explicar cómo avanzó el proceso.",
        "visual": "{topic} protagonistas instituciones retratos archivo",
    },
    {
        "key": "desarrollo",
        "title": "Cómo se desarrolló",
        "weight": 0.13,
        "purpose": "Explicar etapas, mecanismos y cambios con ejemplos verificables.",
        "narration": "A partir de ese punto, {topic} empezó a cambiar. Cada etapa agregó una condición nueva y modificó las posibilidades de la siguiente. En lugar de presentar una sucesión de datos aislados, conviene observar qué cambió, quién tomó la decisión, qué problema intentaba resolver y qué consecuencias tuvo.",
        "visual": "{topic} proceso desarrollo etapas diagrama",
    },
    {
        "key": "inflexion",
        "title": "El punto de inflexión",
        "weight": 0.11,
        "purpose": "Identificar el acontecimiento o decisión que alteró el rumbo.",
        "narration": "En algún momento aparece un cambio que modifica el rumbo de {topic}. Puede ser una decisión, un descubrimiento, una crisis o una nueva condición externa. Lo importante es explicar por qué ese momento fue distinto y qué evidencia permite considerarlo un punto de inflexión, sin exagerar su importancia.",
        "visual": "{topic} acontecimiento cambio punto de inflexión",
    },
    {
        "key": "impacto",
        "title": "Consecuencias e impacto",
        "weight": 0.11,
        "purpose": "Mostrar efectos inmediatos y de largo plazo, con sus límites.",
        "narration": "Las consecuencias no aparecen todas al mismo tiempo ni afectan a todos por igual. Algunas son inmediatas y fáciles de observar; otras se hacen visibles años después. Para entender el impacto de {topic}, hay que separar los resultados documentados de las interpretaciones y reconocer también aquello que no cambió.",
        "visual": "{topic} consecuencias impacto sociedad",
    },
    {
        "key": "debate",
        "title": "Debates y zonas grises",
        "weight": 0.10,
        "purpose": "Contrastar interpretaciones y exponer incertidumbres relevantes.",
        "narration": "No todas las fuentes interpretan {topic} de la misma manera. Algunas diferencias se deben a nueva evidencia; otras, a intereses, métodos o perspectivas distintas. Este contraste no debilita la historia: permite mostrar qué sabemos, qué sigue en discusión y por qué algunas respuestas todavía requieren cautela.",
        "visual": "{topic} debate documentos comparacion fuentes",
    },
    {
        "key": "legado",
        "title": "El legado",
        "weight": 0.09,
        "purpose": "Conectar el proceso histórico con su presencia y significado actuales.",
        "narration": "Mirar {topic} desde el presente permite reconocer qué elementos permanecieron y cuáles fueron transformados. Su legado no depende solamente de lo que ocurrió al principio, sino también de cómo otras generaciones lo interpretaron, lo adaptaron o discutieron sus consecuencias.",
        "visual": "{topic} legado actualidad archivo",
    },
    {
        "key": "cierre",
        "title": "Conclusión",
        "weight": 0.08,
        "purpose": "Responder la pregunta inicial y cerrar sin inventar certezas.",
        "narration": "Al volver a la pregunta inicial, la historia de {topic} aparece como un proceso de decisiones, condiciones y consecuencias, no como una explicación simple atribuible a una sola causa. Lo que queda claro es qué muestran las fuentes y qué preguntas siguen abiertas. Esa diferencia es parte esencial de contar la historia con rigor.",
        "visual": "{topic} conclusión plano final documental",
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

REDDIT_STORY_BLUEPRINT = [
    {
        "key": "hook",
        "title": "El comienzo que no cierra",
        "weight": 0.10,
        "purpose": "Abrir en medio del problema y dejar una pregunta que obligue a seguir.",
        "narration": "Nunca pensé que {topic} iba a terminar convirtiéndose en el peor problema de mi vida. Todo empezó con algo tan cotidiano que ni siquiera le presté atención. Yo confiaba en las personas involucradas, conocía sus costumbres y estaba convencido de que podía anticipar sus reacciones. Pero esa noche recibí una noticia que no tenía sentido. Cuando intenté entenderla, descubrí que alguien me estaba ocultando una parte importante de la historia.",
        "visual": "{topic} historia reddit escena intensa primer plano vertical",
    },
    {
        "key": "contexto",
        "title": "Cómo empezó todo",
        "weight": 0.15,
        "purpose": "Presentar protagonista, vínculos y situación con detalles concretos.",
        "narration": "Para entender lo que pasó, tengo que explicar cómo era todo antes. Éramos un grupo que se conocía desde hacía tiempo y teníamos una rutina bastante normal. Había confianza, chistes internos y problemas que parecían fáciles de resolver hablando. Por eso, cuando apareció la primera contradicción, no pensé que fuera algo grave. Preferí creer la explicación más sencilla y seguir con mi vida. Ahora, mirando hacia atrás, había señales que no quise ver.",
        "visual": "{topic} vida cotidiana casa teléfono mensajes vertical",
    },
    {
        "key": "primer_conflicto",
        "title": "La primera señal",
        "weight": 0.18,
        "purpose": "Introducir una anomalía concreta que cambie la situación.",
        "narration": "Todo cambió cuando apareció un detalle que no encajaba: una conversación, una fecha y una respuesta que se contradecían entre sí. Pregunté directamente qué estaba pasando, pero recibí una explicación demasiado rápida y nadie quiso mostrarme el resto. Una persona cambió de tema; otra me dijo que estaba exagerando. En ese momento decidí dejarlo pasar para evitar una pelea, sin imaginar que esa decisión iba a darles tiempo para preparar otra versión.",
        "visual": "{topic} mensaje sospechoso reacción persona vertical",
    },
    {
        "key": "escalada",
        "title": "Cada vez peor",
        "weight": 0.22,
        "purpose": "Elevar las consecuencias y mostrar decisiones, no repetir el conflicto.",
        "narration": "Durante los días siguientes, las cosas empeoraron. Empecé a revisar lo que había pasado y encontré pequeñas diferencias entre lo que cada uno contaba. Cuando preguntaba por una, aparecía otra excusa; cuando intentaba hablar en privado, alguien intervenía para cortar la conversación. Lo más difícil no era el problema en sí, sino darme cuenta de que la gente en la que confiaba sabía mucho más de lo que decía y esperaba que yo no hiciera preguntas.",
        "visual": "{topic} discusión tensión llamada teléfono vertical",
    },
    {
        "key": "giro",
        "title": "Lo que realmente había pasado",
        "weight": 0.20,
        "purpose": "Revelar una información que reinterprete las pistas anteriores.",
        "narration": "Entonces descubrí el detalle que lo cambió todo: la explicación que me habían dado era cierta solo a medias. Encontré una prueba que conectaba dos hechos que hasta ese momento parecían separados. Había otra persona involucrada y una razón que nadie se había animado a contarme. De golpe, las contradicciones dejaron de parecer casualidad. Entendí por qué habían insistido tanto en que no preguntara y por qué todos repetían exactamente la misma versión.",
        "visual": "{topic} revelación sorpresa prueba documento vertical",
    },
    {
        "key": "cierre",
        "title": "La decisión y la pregunta",
        "weight": 0.15,
        "purpose": "Mostrar la consecuencia y terminar con una pregunta concreta para comentarios.",
        "narration": "Al final tuve que enfrentar a las personas involucradas y tomar una decisión que cambió esa relación para siempre. No voy a decir que todo se resolvió de manera perfecta: quedaron cosas sin explicar y todavía hay alguien que sostiene que yo fui quien exageró. Lo que sí sé es que ya no podía seguir fingiendo que nada había pasado. Todavía no sé si hice lo correcto, por eso quiero preguntarles algo: ¿ustedes habrían hecho lo mismo en mi lugar o creen que me equivoqué?",
        "visual": "{topic} persona reflexionando final historia vertical",
    },
]

FRUTINOVELA_BLUEPRINT = [
    {
        "key": "gancho",
        "title": "El secreto sale a la luz",
        "weight": 0.12,
        "purpose": "Abrir en medio del conflicto con una frase o imagen que deje una pregunta inmediata.",
        "narration": "Nadie en la familia de {characters} esperaba que {topic} terminara así. Pero esa noche, justo cuando parecía que todo estaba resuelto, alguien dijo una frase que lo cambió todo.",
        "visual": "{topic} {characters} personajes fruta telenovela escena dramática vertical",
    },
    {
        "key": "presentacion",
        "title": "Lo que parecía perfecto",
        "weight": 0.16,
        "purpose": "Recordar quiénes son los personajes y qué quieren, sin explicar de más.",
        "narration": "Hasta ese momento, {characters} tenían algo que proteger. Había promesas, celos y una confianza que parecía imposible de romper. Lo que nadie veía era que dos versiones de la misma historia estaban a punto de chocar.",
        "visual": "{topic} {characters} personajes fruta familia casa colores vivos",
    },
    {
        "key": "conflicto",
        "title": "La traición",
        "weight": 0.20,
        "purpose": "Hacer avanzar el conflicto con una decisión concreta de un personaje.",
        "narration": "Entre {characters}, la discusión empezó por algo pequeño, pero terminó revelando lo que todos venían ocultando. Uno de ellos tomó una decisión a espaldas del resto. Y cuando el mensaje llegó al teléfono equivocado, ya no hubo forma de fingir que no había pasado nada.",
        "visual": "{topic} {characters} personajes fruta discusión traición melodrama",
    },
    {
        "key": "giro",
        "title": "La verdad inesperada",
        "weight": 0.20,
        "purpose": "Cambiar el sentido de lo ocurrido con una revelación dramática coherente.",
        "narration": "Entonces apareció una prueba que nadie de {characters} había visto. La persona señalada no era quien había empezado todo. Alguien más había movido las piezas desde el principio, y tenía un motivo que podía destruir a toda la familia.",
        "visual": "{topic} {characters} personaje fruta descubre secreto carta revelación",
    },
    {
        "key": "confrontacion",
        "title": "Cara a cara",
        "weight": 0.18,
        "purpose": "Enfrentar a los personajes y dejar una consecuencia emocional clara.",
        "narration": "Por primera vez, {characters} dejaron de bajar la mirada. Las preguntas se convirtieron en acusaciones y una sola respuesta podía cambiar para siempre la relación entre ellos. Pero antes de que alguien pudiera explicar lo que sabía, sonó el timbre.",
        "visual": "{topic} {characters} personajes fruta enfrentamiento puerta noche",
    },
    {
        "key": "cliffhanger",
        "title": "Continuará…",
        "weight": 0.14,
        "purpose": "Cerrar con un cliffhanger concreto que invite a ver el siguiente episodio.",
        "narration": "Del otro lado de la puerta había alguien que {characters} creían que se había ido para siempre. Traía una noticia y un nombre escrito en un papel. Cuando el protagonista lo leyó, entendió que lo peor todavía no había empezado. ¿Qué va a pasar ahora? Esto no termina acá.",
        "visual": "{topic} {characters} personaje fruta silueta puerta cliffhanger telenovela",
    },
]

BLUEPRINTS = {
    "documentary": DOCUMENTARY_BLUEPRINT,
    "short": SHORT_BLUEPRINT,
    "listicle": LISTICLE_BLUEPRINT,
    "pov": POV_BLUEPRINT,
    "explainer": EXPLAINER_BLUEPRINT,
    "quote": QUOTE_BLUEPRINT,
    "frutinovela": FRUTINOVELA_BLUEPRINT,
    "reddit_story": REDDIT_STORY_BLUEPRINT,
}

def _hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]


def blueprint(kind: str) -> list[dict]:
    """Blueprint narrativo por plantilla de guion."""
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

    source_notes = [] if script_kind in {"frutinovela", "reddit_story"} else [
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

    # Preserve the full documentary structure even when research is sparse.
    # Evidence is distributed only where available; missing evidence is disclosed below.
    if evidence_sentences:
        evidence_sentences = evidence_sentences[:max(len(beats), int(target / 10))]

    claims = _claims([n for n in notes if n is not source_note])
    rnd = random.Random(_hash(f"{project.get('id')}-{topic}-{kind}"))
    rnd.shuffle(claims)

    scenes = []
    claim_index = 0
    for idx, beat in enumerate(beats):
        characters = (project.get("content_pillars") or topic or "los personajes").strip()
        narration = beat["narration"].format(topic=topic, characters=characters)
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
        hook_style = (project.get("hook_style") or "Dato sorprendente").strip()
        if idx == 0:
            hook_prefixes = {
                "Pregunta intrigante": f"¿Qué hay detrás de {topic}? ",
                "Dato sorprendente": f"Hay un detalle de {topic} que vale la pena conocer: ",
                "Situación en medio de la acción": f"Todo parece normal, hasta que aparece un detalle clave en {topic}. ",
                "Error o mito que desmontar": f"Hay una idea sobre {topic} que conviene revisar. ",
                "Misterio sin resolver": f"Hay una pregunta sobre {topic} que todavía merece atención. ",
                "Afirmación polémica verificable": f"Sobre {topic}, la explicación más repetida no siempre alcanza. ",
            }
            tone_prefixes = {
                "Dinámico y cercano": "Mirá este detalle: ",
                "Misterioso y tenso": "Prestá atención a lo que aparece después: ",
                "Documental y riguroso": "Vamos a los datos: ",
                "Humorístico e irónico": "Parece sencillo, pero tiene su vuelta: ",
                "Emocional y reflexivo": "La historia detrás de este tema merece atención: ",
                "Enérgico y provocador": "Este es el punto que no hay que pasar por alto: ",
            }
            narration = hook_prefixes.get(hook_style, "") + tone_prefixes.get(project.get("tone", ""), "") + narration
        if idx == len(beats) - 1:
            cta = (project.get("cta") or "").strip()
            default_cta_starts = (
                "Guardá este vídeo", "Contame abajo", "Si te quedó una duda",
                "¿Qué parte te sorprendió", "¿Vos qué opinás", "Compartilo con alguien",
                "Seguime para ver más", "En el próximo seguimos",
            )
            for phrase in default_cta_starts:
                if phrase in narration:
                    narration = narration.split(phrase, 1)[0].rstrip()
            cta_lines = {
                "Hacé una pregunta concreta al final": "¿Qué parte te sorprendió más? Te leo en los comentarios.",
                "Invitá a comentar una opinión": "¿Vos qué opinás? Dejá tu punto de vista en los comentarios.",
                "Invitá a compartir el Short": "Compartilo con alguien a quien le pueda interesar.",
                "Invitá a seguir el canal": "Seguime para ver más historias como esta.",
            }
            if cta in cta_lines:
                narration = narration.rstrip() + " " + cta_lines[cta]
        visual_query = beat["visual"].format(topic=topic, characters=characters)
        visual_style = (project.get("visual_style") or "").strip()
        style_search_terms = {
            "automatico": "Fotografía de archivo histórica",
            "cinematico": "Fotografía de archivo histórica con iluminación cinematográfica",
            "realista": "Fotografía de archivo realista",
            "anime": "Ilustración estilo anime",
            "pixel_art": "Pixel art",
            "noir": "Fotografía en blanco y negro estilo cine noir",
            "vintage": "Fotografía vintage sepia",
            "cyberpunk": "Ilustración cyberpunk",
            "acuarela": "Ilustración en acuarela",
            "comic": "Ilustración de cómic",
        }
        if visual_style:
            visual_query += " " + style_search_terms.get(visual_style, visual_style)
        # El estilo se usa como pista de búsqueda y como tratamiento local del render.
        scenes.append(
            {
                "idx": idx,
                "title": beat["title"],
                "beat": beat["key"],
                "purpose": beat["purpose"],
                "narration": narration,
                "visual_query": visual_query,
                "duration_target_sec": duration,
                "transition": "fundido" if beat["key"] in ("apertura", "cierre") else "corte",
                "status": "borrador",
            }
        )

    if script_kind == "frutinovela" and project.get("series_context") and scenes:
        recap = str(project["series_context"]).strip()
        scenes[0]["narration"] = (
            "En el capítulo anterior: " + recap[:420] +
            " Y ahora, cuando todos creían que podían seguir adelante, " +
            scenes[0]["narration"]
        )
    unused = [n for n in notes if n is not source_note and (n.get("claim") or "").strip() not in claims[:claim_index]]
    return {
        "title": project.get("title") or f"Short: {topic}",
        "kind": kind,
        "topic": topic,
        "scenes": scenes,
        "warnings": [
            (
                "Relato original estilo Reddit: revisá coherencia, tono y edición antes de publicar."
                if script_kind == "reddit_story"
                else "Ficción original por episodios: revisá continuidad, personajes y diálogos antes de publicar."
                if script_kind == "frutinovela"
                else "Guion estructurado con extractos de una fuente de orientación; contrastar datos con fuentes independientes antes de publicar."
                if source_note and evidence_sentences
                else "Borrador de plantilla local sin evidencia suficiente: no publicar automáticamente."
            ),
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



def regenerate_scene_with_ollama(
    url: str, model: str, project: dict, scene: dict, variant: int = 0
) -> dict:
    """Regenera una sola escena con el modelo local, sin tocar las demás."""
    original = str(scene.get("narration") or "").strip()
    template_id = str(project.get("template") or "")
    is_fiction = template_id in {"frutinovela", "reddit_story"}
    brief = (
        "Es ficción original. Conservá los personajes, sus relaciones y la continuidad. "
        "Mejorá el ritmo, los detalles concretos y la tensión sin resolver toda la trama."
        if is_fiction else
        "Es documental. Conservá todos los hechos, nombres, fechas, cifras y matices del texto. "
        "No agregues datos, causas, citas ni afirmaciones que no estén en el original. "
        "Mejorá claridad oral, ritmo y precisión sin cambiar el significado."
    )
    prompt = (
        "Reescribí únicamente esta escena de un video en español rioplatense natural. "
        + brief
        + " Evitá relleno, frases genéricas, repeticiones y tono robótico. "
        "Mantené una longitud parecida al original (no más del doble ni menos de la mitad). "
        "Devolvé solo JSON válido con esta forma: {\"narration\":\"...\"}.\n"
        f"Título del proyecto: {project.get('title') or ''}\n"
        f"Tema: {project.get('topic') or ''}\n"
        f"Escena: {scene.get('title') or ''}\n"
        f"Texto original: {original}"
    )
    raw = expand_with_ollama(url, model, prompt, timeout=180).strip()
    if raw.startswith(chr(96) * 3):
        raw = re.sub(r"^\x60{3}(?:json)?\s*|\s*\x60{3}$", "", raw, flags=re.IGNORECASE)
    first, last = raw.find("{"), raw.rfind("}")
    if first < 0 or last <= first:
        raise RuntimeError("El modelo local no devolvió JSON válido para la escena.")
    data = json.loads(raw[first:last + 1])
    narration = str(data.get("narration") or "").strip() if isinstance(data, dict) else ""
    if len(narration) < 40:
        raise RuntimeError("El modelo local devolvió una escena vacía o demasiado corta.")
    old_words = max(1, len(original.split()))
    new_words = len(narration.split())
    if new_words < max(8, round(old_words * 0.5)) or new_words > max(24, round(old_words * 2)):
        raise RuntimeError("La escena regenerada se aleja demasiado de la duración original.")
    return {
        "narration": narration,
        "status": "borrador",
        "note": "Escena regenerada con modelo local Qwen/Ollama; revisá el resultado antes de renderizar.",
        "writer": "ollama-local-scene",
    }


def ollama_available(url: str) -> bool:
    if not url:
        return False
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/api/tags", timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False


def ollama_model_available(url: str, model: str) -> bool:
    if not ollama_available(url):
        return False
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/api/tags", timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return any(
            item.get("name") == model or str(item.get("name", "")).startswith(model + ":")
            for item in data.get("models", [])
        )
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




def fiction_word_range(target_seconds: int) -> tuple[int, int]:
    """Calcula una extensión de guion coherente con la duración del Short."""
    seconds = max(15, min(180, int(target_seconds or 90)))
    minimum = max(70, round(seconds * 2.1))
    maximum = max(minimum + 20, round(seconds * 2.5))
    return minimum, maximum


def rewrite_fiction_with_ollama(url: str, model: str, project: dict, script: dict) -> dict:
    """Escribe ficción coherente usando solo un modelo Ollama local, sin servicios pagos."""
    scenes = script.get("scenes") or []
    outline = [
        {
            "idx": scene.get("idx"),
            "title": scene.get("title"),
            "duration_target_sec": scene.get("duration_target_sec"),
        }
        for scene in scenes
    ]
    template_id = project.get("template") or ""
    target_seconds = max(15, min(180, int(project.get("duration_target_sec") or 90)))
    min_words, max_words = fiction_word_range(target_seconds)
    target_words = f"entre {min_words} y {max_words} palabras (aproximadamente {target_seconds} segundos de voz)"
    if template_id == "frutinovela":
        brief = (
            "Es una telenovela vertical por episodios. Conservá exactamente los nombres, personalidades "
            "y relaciones de los personajes. Continuá el cliffhanger del episodio anterior sin contradecirlo. "
            "Cada escena debe avanzar la misma trama; incluí acciones concretas, diálogos breves cuando sumen "
            "y un cliffhanger nuevo al final. No reinicies la historia ni resuelvas todo de golpe."
        )

    else:
        brief = (
            "Es un relato ORIGINAL con ritmo de historia narrada en comunidades tipo Reddit; no afirmes que "
            "es una publicación real ni copies historias ajenas. Construí una sola historia coherente en primera "
            "persona, con detalles cotidianos concretos, tensión creciente, un giro que se prepare con pistas "
            "y una decisión final que invite a debatir."
        )

    prompt = (
        "Redactá un guion audiovisual en español rioplatense natural. " + brief + " "
        "Evitá frases genéricas, repeticiones, explicaciones meta y relleno. "
        f"La narración completa debe tener {target_words}. "
        "Respetá exactamente la cantidad y el orden de escenas del esquema; distribuí la historia "
        "progresivamente y no repitas el mismo texto en distintas escenas. "
        "Devolvé únicamente JSON válido con esta forma: "
        "{\"scenes\":[{\"idx\":0,\"narration\":\"...\"}]}\n\n"
        f"Tipo de serie: {template_id}\n"
        f"Título: {project.get('title') or ''}\n"
        f"Premisa/tema del episodio: {project.get('topic') or project.get('title') or ''}\n"
        f"Personajes y relaciones: {project.get('content_pillars') or 'Elegí un elenco pequeño y mantenelo estable'}\n"
        f"Continuidad anterior: {project.get('series_context') or 'Es el primer episodio; presentá la situación y los vínculos'}\n"
        f"Público: {project.get('audience') or 'Público general'}\n"
        f"Tono: {project.get('tone') or 'Dramático y cercano'}\n"
        f"Duración objetivo: {target_seconds} segundos\n"
        f"Esquema de escenas: {json.dumps(outline, ensure_ascii=False)}"
    )
    raw = expand_with_ollama(url, model, prompt, timeout=240)
    cleaned = raw.strip()
    if cleaned.startswith(chr(96) * 3):
        cleaned = re.sub(r"^\x60{3}(?:json)?\s*|\s*\x60{3}$", "", cleaned, flags=re.IGNORECASE)
    first, last = cleaned.find("{"), cleaned.rfind("}")
    if first < 0 or last <= first:
        raise RuntimeError("Ollama no devolvió un JSON reconocible para la ficción.")
    data = json.loads(cleaned[first:last + 1])
    generated = data.get("scenes") if isinstance(data, dict) else None
    if not isinstance(generated, list) or len(generated) != len(scenes):
        raise RuntimeError("Ollama devolvió una cantidad de escenas distinta a la solicitada.")
    by_idx = {int(item.get("idx", -1)): item for item in generated if isinstance(item, dict)}
    rewritten = []
    for scene in scenes:
        item = by_idx.get(int(scene.get("idx", -1)))
        narration = str((item or {}).get("narration") or "").strip()
        if len(narration) < 50:
            raise RuntimeError(f"Ollama dejó vacía o demasiado corta la escena {scene.get('idx')}.")
        rewritten.append({**scene, "narration": narration})
    total_words = sum(len(str(scene.get("narration") or "").split()) for scene in rewritten)
    if total_words < round(min_words * 0.8) or total_words > round(max_words * 1.2):
        raise RuntimeError(
            f"Ollama devolvió {total_words} palabras; para {target_seconds} segundos "
            f"se esperaban aproximadamente {min_words}-{max_words}. Se usará el guion de respaldo."
        )
    return {
        **script,
        "scenes": rewritten,
        "warnings": [
            *script.get("warnings", []),
            "Guion de ficción redactado con Ollama local; revisá continuidad y diálogos antes de publicar.",
        ],
        "writer": "ollama-local-fiction",
        "evidence_sources": 0,
    }


def rewrite_with_ollama(url: str, model: str, project: dict, script: dict, notes: list[dict]) -> dict:
    """Reescribe el guion con evidencia y ajusta la extensión al formato real."""
    source_notes = [
        note for note in notes
        if note.get("source_url") and len((note.get("claim") or "")) >= 300
    ][:5]
    if not source_notes:
        raise RuntimeError("No hay fuentes documentales suficientes para redactar el guion.")

    scenes = script.get("scenes") or []
    if not scenes:
        raise RuntimeError("El esquema del guion no contiene escenas.")

    target_seconds = int(project.get("duration_target_sec") or 600)
    is_longform = target_seconds > 180 and project.get("kind") != "short"
    if is_longform:
        target_seconds = max(480, min(1200, target_seconds))
        min_words = round(target_seconds * 1.8)
        max_words = round(target_seconds * 2.35)
        format_brief = (
            "Es un DOCUMENTAL HORIZONTAL DE FORMATO LARGO para YouTube. No es un Short ni un resumen. "
            "Construí un arco documental completo: pregunta inicial, contexto, antecedentes, protagonistas, "
            "desarrollo cronológico o causal, punto de inflexión, consecuencias, debates y conclusión. "
            "Cada escena debe aportar información nueva, ejemplos concretos y transiciones narrativas. "
            "No inventes datos, fechas, nombres, citas ni relaciones causales que no aparezcan en las fuentes. "
            "Si la evidencia no alcanza para una afirmación, explicá el límite en vez de rellenar."
        )
        target_label = f"entre {min_words} y {max_words} palabras para aproximadamente {target_seconds // 60} minutos"
        timeout = 900
    else:
        target_seconds = max(15, min(180, target_seconds))
        min_words = max(70, round(target_seconds * 1.8))
        max_words = max(min_words + 20, round(target_seconds * 2.4))
        format_brief = (
            "Es un YouTube Short vertical, autónomo y dinámico. Abrí con un hook inmediato, desarrollá "
            "una sola idea central y cerrá con una conclusión o pregunta concreta."
        )
        target_label = f"entre {min_words} y {max_words} palabras para aproximadamente {target_seconds} segundos"
        timeout = 300

    outline = [
        {
            "idx": scene.get("idx"),
            "title": scene.get("title"),
            "purpose": scene.get("purpose"),
            "duration_target_sec": scene.get("duration_target_sec"),
        }
        for scene in scenes
    ]
    prompt = (
        "Escribí un guion audiovisual original en español rioplatense natural. "
        + format_brief + " "
        "Usá exclusivamente los datos del material de referencia para las afirmaciones factuales: "
        "parafraseá, contrastá coincidencias y discrepancias y no copies párrafos. "
        "Evitá frases genéricas, repeticiones, explicaciones meta y relleno. "
        f"La narración completa debe tener {target_label}. "
        "Respetá exactamente la cantidad y el orden de escenas del esquema. Distribuí la extensión "
        "proporcionalmente a la duración de cada escena; ninguna escena debe quedar como una frase de resumen. "
        "Desarrollá los hechos con contexto, explicación y consecuencias, sin repetir una idea para alcanzar "
        "la cantidad de palabras. Devolvé únicamente JSON válido con esta forma: "
        "{\"scenes\":[{\"idx\":0,\"narration\":\"...\"}]}\n\n"
        f"Tema: {project.get('topic') or project.get('title')}\n"
        f"Título: {project.get('title') or ''}\n"
        f"Duración total objetivo: {target_seconds} segundos\n"
        f"Público: {project.get('audience', 'Público general')}\n"
        f"Tono: {project.get('tone', 'Documental y riguroso')}\n"
        f"Esquema: {json.dumps(outline, ensure_ascii=False)}\n"
        "MATERIAL DE REFERENCIA (no agregues hechos externos):\n"
        + "\n\n".join(
            f"FUENTE: {note.get('source_url', '')}\nCONTENIDO: {(note.get('claim') or '')[:5000]}"
            for note in source_notes
        )
    )
    raw = expand_with_ollama(url, model, prompt, timeout=timeout)
    cleaned = raw.strip()
    if cleaned.startswith(chr(96) * 3):
        cleaned = re.sub(r"^\x60{3}(?:json)?\s*|\s*\x60{3}$", "", cleaned, flags=re.IGNORECASE)
    first, last = cleaned.find("{"), cleaned.rfind("}")
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
        if len(narration) < 80:
            raise RuntimeError(f"Ollama dejó vacía o demasiado corta la escena {scene.get('idx')}.")
        rewritten.append({**scene, "narration": narration})

    total_words = sum(len(str(scene.get("narration") or "").split()) for scene in rewritten)
    if total_words < round(min_words * 0.8):
        raise RuntimeError(
            f"Ollama devolvió {total_words} palabras; para {target_seconds} segundos se requieren "
            f"al menos {round(min_words * 0.8)}. Se conserva el borrador de respaldo."
        )
    if is_longform and total_words > round(max_words * 1.2):
        raise RuntimeError("Ollama excedió la extensión prevista; se conserva el borrador de respaldo.")

    return {
        **script,
        "scenes": rewritten,
        "warnings": [
            *script.get("warnings", []),
            "Guion reescrito con Ollama local a partir de las fuentes del proyecto; verificá afirmaciones y atribuciones antes de publicar.",
        ],
        "writer": "ollama-local",
        "evidence_sources": len(source_notes),
    }
