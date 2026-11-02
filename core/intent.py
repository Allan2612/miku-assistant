"""
Miku Assistant - What a heard phrase is, by its words: noise, an echo of her own voice, a hide order, a goodbye,
an order or chat. Every word list lives here, so a phrase misheard in a log is fixed in one place and checked in
tests/test_intent.py, instead of in rules spread over the pipeline and the brain that disagree.
"""

from __future__ import annotations

import re
from typing import Iterable

# Start of a phrase: Whisper often keeps the wake phrase ("Hey Miku, abre...")
WAKE_PREFIX = r"^(?:(?:hey|oye|ey)\s+)?(?:miku\s*[,.]?\s*)?"

# "Miku" as Whisper writes it ("Hey Miku", "Ey, Micu", "Miko"); not "Mike" nor "mi cuerpo"
_SAYS_MIKU = re.compile(r"\bm[iíy]\s?[kcq]{1,2}[uúo]\b", re.IGNORECASE)

# What Whisper writes for noise or silence: it learned it from YouTube subtitles (seen twice in the log: 05:13 and
# 05:23, both "¡Suscríbete!"). Never a real request
_HALLUCINATIONS = (
    "¡Suscríbete!", "Suscríbete al canal", "¡Suscríbete al canal!", "Gracias por ver", "Gracias por ver el video",
    "Gracias por ver el vídeo", "¡Gracias por ver!", "Subtítulos por la comunidad de Amara.org",
    "Subtítulos realizados por la comunidad de Amara.org", "Gracias por su atención", "Hasta la próxima",
)

FAREWELL_KEYWORDS = [
    "adios", "adiós", "chao", "chau", "hasta luego", "nos vemos",
    "gracias, eso es todo", "eso es todo", "eso sería todo", "nada más", "vete", "duérmete", "duermete",
    "ocúltate", "ocultate", "escóndete", "escondete", "desaparece", "bye", "goodbye", "eso era todo",
    # usted forms and how Whisper writes them (log 27-oct: "Nada, nada. Cúltese.", "Miku, apaguece!")
    "ocúltese", "ocultese", "cúltese", "cultese", "escóndase", "escondase", "váyase", "vayase",
    "apágate", "apagate", "apáguese", "apaguese", "apaguece", "apángese", "apangese", "apángate", "apangate",
    "no te necesito", "ya no te necesito", "ya terminé", "ya termine", "puedes irte", "te puedes ir",
]
# Goodbyes only when they are the WHOLE phrase: "¿ya está abierto Spotify?" or "gracias por abrirlo, ahora..."
# are not (punctuation and "Miku" are ignored)
FAREWELL_EXACT = {
    "ya está", "ya esta", "listo", "ya", "nada", "no nada", "gracias", "muchas gracias", "gracias miku",
    "listo gracias", "ok gracias", "vale gracias", "no gracias", "nada gracias", "ya está gracias", "ya esta gracias",
    "así está bien", "asi esta bien", "está bien gracias", "esta bien gracias",
    "no era nada", "me equivoqué", "me equivoque", "olvídalo", "olvidalo", "déjalo", "dejalo", "no importa",
}
# Orders to hide: she just goes, without a word
HIDE_NOW = {"ocúltate", "ocultate", "ocúltese", "ocultese", "cúltese", "cultese", "escóndete", "escondete",
            "escóndase", "escondase", "vete", "váyase", "vayase", "desaparece", "apágate", "apagate", "apáguese",
            "apaguese", "apaguece", "apángese", "apangese", "apángate", "apangate", "duérmete", "duermete",
            "puedes irte", "te puedes ir", "puede irse"}
# A short phrase made only of these, with at least one goodbye word, is a goodbye: "listo, eso era todo, gracias"
_BYE_WORDS = {"gracias", "chao", "chau", "adiós", "adios", "bye", "olvídalo", "olvidalo", "déjalo", "dejalo", "listo",
              "nada"}
_BYE_FILLER = {"ya", "no", "ok", "vale", "bueno", "muchas", "mil", "eso", "es", "era", "sería", "seria", "todo", "así",
               "asi", "está", "esta", "bien", "por", "ahora", "de", "verdad", "entonces", "pues", "más", "mas"}
# Words that do not change a hide order: "Nada, nada. Ocúltese", "Ya, Miku, vete"
_HIDE_FILLER = {"ya", "nada", "ok", "vale", "bueno", "listo", "ahora", "porfa", "por", "favor"}

# Orders as said to her, whole words. Usted forms and Whisper's spellings with a pronoun too: "Póngale pausa y
# sérame todas las ventanas" only paused (log 1-nov)
_ORDER_VERBS = (
    r"(?:abre|[aá]breme|cierra|pon|ponme|sube|s[uú]bele|baja|b[aá]jale|busca|reproduce|minimiza|maximiza|anota"
    r"|apunta|recu[eé]rdame|copia|silencia|pausa|apaga|quita"
    r"|cierre|abra|ponga|suba|baje|busque|minimice|maximice|quite|\w{2,}(?:ame|eme|ale|ele))"
)
_ORDER = re.compile(rf"\b{_ORDER_VERBS}\b", re.IGNORECASE)
# A second order after the first: "abre Spotify y pon el volumen al 30"
_CHAINED_ORDER = re.compile(
    rf"(?:\by\b|,|\bluego\b|\bdespu[eé]s\b|\btambi[eé]n\b)\s*(?:me\s+)?{_ORDER_VERBS}\b", re.IGNORECASE
)
# An order in the first words, by its stem: Whisper splits and misspells them ("Cierra me OBS Studio", log 27-oct)
_ORDER_START = re.compile(
    # With their accents too: "súbele", "ábreme", "póngale"
    r"^\W*(?:\w+\W+){0,2}?(?:[aá]br|cierr|p[oó]n|ap[aá]g|s[uú]b|b[aá]j|b[uú]sc|reproduc|minimiz|maximiz|an[oó]t"
    r"|ap[uú]nt|recu[eé]rd|c[oó]pi|silenci|paus|quit)\w*",
    re.IGNORECASE,
)

# The user asks about the screen: a screenshot rides in the same single request (never taken otherwise)
_SCREEN = re.compile(
    # "la pantalla derecha" is a monitor, not "look at my screen": that screenshot cost 3.6 MB and seconds (log 1-nov)
    r"\b(?:(?:mi |la |esta |en )?pantalla(?!\s+(?:de\s+la\s+)?(?:derecha|izquierda|principal|secundaria|uno|dos|\d))"
    r"|qu[eé] ves|mira (?:esto|esta|este|aqu[ií])|este error|esta ventana)\b",
    re.IGNORECASE,
)
# Something on screen by position: "ábreme la segunda opción" (log 06:13: it searched again, blind)
_POSITION = re.compile(
    r"\b(?:(?:primer|segund|tercer|cuart|quint|últim|ultim)[oa]?\s+(?:opci[oó]n|resultado|enlace|link|v[ií]deo)"
    r"|(?:ese|esa|este|esta)\s+(?:enlace|link|resultado|opci[oó]n|bot[oó]n))\b",
    re.IGNORECASE,
)


def normalize(text: str) -> str:
    """Lowercase letters, digits and spaces only: "¿Sí?" -> "sí"."""
    return "".join(c for c in text.lower() if c.isalnum() or c == " ").strip()


def bare(text: str) -> str:
    """Words only, without "Miku" and repeats: "Nada, nada, Miku." -> "nada" (log 26-oct: cost a request)."""
    words = [w for w in re.findall(r"[\wáéíóúñü]+", text.lower()) if w != "miku"]
    return " ".join(w for i, w in enumerate(words) if i == 0 or w != words[i - 1])


_HALLUCINATIONS_NORMALIZED = {normalize(p) for p in _HALLUCINATIONS}


def says_miku(text: str) -> bool:
    return bool(_SAYS_MIKU.search(text))


def is_farewell(text: str) -> bool:
    """A short goodbye, by whole words: "vete a la configuración y..." is not one (H-027). True even with an order
    in it ("adiós, cierra Spotify"): she does the order, then hides."""
    norm = text.lower().strip()
    if len(norm.split()) > 6:
        return False
    words_only = bare(norm)
    if words_only in FAREWELL_EXACT:
        return True
    # Any short mix of goodbye and filler words: "Olvídalo, muchas gracias" was not in the list and she stayed
    # (log 27-oct). Whisper writes "olvídalo" as "olvíalo" too: any "olvi..." counts
    words = words_only.split()
    bye = [w for w in words if w in _BYE_WORDS or w.startswith(("olvi", "olví"))]
    if bye and all(w in _BYE_FILLER or w in bye for w in words):
        return True
    return any(re.search(r"\b" + re.escape(kw) + r"\b", norm) for kw in FAREWELL_KEYWORDS)


def is_hide_order(text: str) -> bool:
    """"Ocúltate", "Nada, nada. Cúltese": she goes without a word ("¡De nada!" answered an "Adiós", log 06:17)."""
    return " ".join(w for w in bare(text).split() if w not in _HIDE_FILLER) in HIDE_NOW


def mentions_order(text: str) -> bool:
    return bool(_ORDER.search(text))


def starts_with_order(text: str) -> bool:
    return bool(_ORDER_START.search(text))


def has_chained_orders(text: str) -> bool:
    """Several orders in one phrase (minus the wake phrase: the comma in "Hey Miku, abre..." is not a second one)."""
    return bool(_CHAINED_ORDER.search(re.sub(WAKE_PREFIX, "", text.lower().strip().strip("¡!¿?.,;: "))))


def asks_about_screen(text: str) -> bool:
    return bool(_SCREEN.search(text))


def points_at_screen(text: str) -> bool:
    return bool(_POSITION.search(text))


def classify(text: str, cues: Iterable[str] = (), last_answer: str = "") -> str:
    """One of: noise, echo, hide, farewell, order, chat.

    cues: what she just said to open the mic ("¿Sí?"); only then is "¡Sí!" her echo, in a conversation it is the
    user's answer (log 1-nov: ignored, she left). last_answer: the mic opens right after she speaks, so the tail of
    her own answer must not come back as the user's next question.
    """
    heard = normalize(text)
    # Whisper "hears" YouTube outros in noise: "¡Suscríbete!" made Gemini reopen the last web page (log, 24-oct)
    if not heard or heard in _HALLUCINATIONS_NORMALIZED or "amaraorg" in heard.replace(" ", ""):
        return "noise"
    cue_set = {normalize(c) for c in cues}
    if heard in cue_set or (cue_set and heard == "si"):
        return "echo"
    if len(heard.split()) >= 2 and heard in normalize(last_answer):
        return "echo"
    # A plain goodbye; with an order in it ("adiós, cierra Spotify") the order comes first
    if is_farewell(text) and not mentions_order(text):
        return "hide" if is_hide_order(text) else "farewell"
    if mentions_order(text) or starts_with_order(text):
        return "order"
    return "chat"
