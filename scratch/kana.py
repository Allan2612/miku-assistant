"""
Spanish text -> katakana, so a Japanese TTS voice reads Spanish with a Japanese accent (how Miku would speak it).

Spanish spelling is nearly phonetic: normalize it to sounds (c/qu -> k, ll -> y, j/ge -> h, z -> s...), split
into consonant+vowel units, and write each as katakana. A consonant with no vowel after it gets the Japanese
filler vowel (u, or o after t/d), except n (ン). Punctuation becomes its Japanese form.

Run: core\\.venv\\Scripts\\python.exe scratch\\kana.py "¡Hola! ¿Qué vamos a hacer hoy?"
"""

import re
import sys
import unicodedata

VOWELS = "aeiou"
# consonant (as a sound) -> katakana for a, e, i, o, u
ROWS = {
    "": "アエイオウ", "k": "カケキコク", "g": "ガゲギゴグ", "s": ["サ", "セ", "スィ", "ソ", "ス"],
    "t": ["タ", "テ", "ティ", "ト", "トゥ"], "d": ["ダ", "デ", "ディ", "ド", "ドゥ"], "n": "ナネニノヌ",
    "h": "ハヘヒホフ", "b": "バベビボブ", "p": "パペピポプ", "m": "マメミモム", "y": ["ヤ", "イェ", "イ", "ヨ", "ユ"],
    "r": "ラレリロル", "l": "ラレリロル", "f": ["ファ", "フェ", "フィ", "フォ", "フ"], "ch": ["チャ", "チェ", "チ", "チョ", "チュ"],
    "ny": ["ニャ", "ニェ", "ニ", "ニョ", "ニュ"], "w": ["ワ", "ウェ", "ウィ", "ウォ", "ウ"],
}
ORDER = "aeiou"  # ROWS columns are a, e, i, o, u
CODA = {"n": "ン", "t": "ト", "d": "ド", "s": "ス", "r": "ル", "l": "ル", "k": "ク", "g": "グ", "b": "ブ",
        "p": "プ", "m": "ム", "f": "フ", "h": "フ", "ch": "チ", "y": "イ"}
PUNCT = {".": "。", ",": "、", "!": "！", "?": "？", "¡": "", "¿": "", ":": "、", ";": "、"}


def _sounds(word: str) -> str:
    """Spanish spelling -> one letter per sound (ch and ny stay as two letters, handled by the tokenizer)."""
    w = word.lower().replace("ñ", "ny")
    w = "".join(c for c in unicodedata.normalize("NFD", w) if not unicodedata.combining(c))
    w = re.sub(r"(?<!c)h", "", w)  # the written h is silent; it must go before j/ge become the "h" sound
    # Upper-case placeholders (the text is lower-case) keep ch and gue/gui out of the c -> k and ge -> h rules
    w = w.replace("ch", "C")
    w = re.sub(r"gu(?=[ei])", "G", w)
    w = re.sub(r"ll", "y", w)
    w = re.sub(r"qu(?=[ei])", "k", w)
    w = re.sub(r"g(?=[ei])", "h", w)
    w = re.sub(r"c(?=[ei])", "s", w)
    w = w.replace("c", "k").replace("q", "k").replace("z", "s").replace("j", "h").replace("v", "b")
    w = w.replace("x", "ks").replace("rr", "r").replace("w", "u")
    w = re.sub(r"y$", "i", w)  # "hoy", "muy": final y is a vowel
    return w.replace("C", "ch").replace("G", "g")


def _word(word: str) -> str:
    s = _sounds(word)
    out, i = [], 0
    while i < len(s):
        cons = ""
        for c in ("ch", "ny"):
            if s.startswith(c, i):
                cons, i = c, i + 2
                break
        else:
            if s[i] not in VOWELS:
                cons, i = s[i], i + 1
        if cons and (i >= len(s) or s[i] not in VOWELS):  # no vowel follows: coda
            out.append(CODA.get(cons, ""))
            continue
        vowel = s[i] if i < len(s) else "u"
        i += 1
        row = ROWS.get(cons, ROWS[""])
        out.append(row[ORDER.index(vowel)])
    return "".join(out)


def to_katakana(text: str) -> str:
    parts = re.findall(r"[^\W\d_]+|\d+|[^\w\s]|\s+", text)
    return "".join(PUNCT.get(p, p) if not p.strip() or not p[0].isalnum() else
                   (_word(p) if p[0].isalpha() else p) for p in parts).strip()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    for t in sys.argv[1:] or ["¡Hola! ¿Qué vamos a hacer hoy?", "¡Listo! Ya te puse la canción en YouTube, ¡a disfrutar!",
                              "Mmm... no encontré esa nota. ¿Me la repites, porfa?", "¡Oye, recuerda: tomar agua!"]:
        print(t, "->", to_katakana(t))
