"""H-027: farewell detection only for short goodbyes, by whole words.

Run: core\\.venv\\Scripts\\python.exe -m tests.test_farewell  (or with pytest)
"""

from core.llm import MikuBrain


def is_farewell(text):
    return MikuBrain.is_farewell(None, text)


def test_farewell():
    for text in ("adiós", "Adiós Miku", "gracias, eso es todo", "chao", "vete"):
        assert is_farewell(text), text
    for text in ("vete a la configuración y cambia el idioma de windows", "es un trabajo chaotico", "abre chrome"):
        assert not is_farewell(text), text


if __name__ == "__main__":
    test_farewell()
    print("ok")
