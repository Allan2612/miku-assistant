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


def test_done_phrases_are_goodbyes_only_when_alone():
    # "When I tell her it's done or I don't need her, she should hide" (user, 24-oct)
    for text in ("Ya está.", "¡Ya está, Miku!", "Eso es todo. Déjalo ahí.", "No te necesito", "ya no te necesito",
                 "Gracias.", "Muchas gracias", "listo", "Nada.", "No, nada", "chau", "nada más", "así está bien"):
        assert is_farewell(text), text
    for text in ("¿ya está abierto spotify?", "gracias por abrirlo, ahora sube el volumen", "nada de eso, abre discord",
                 "listo para jugar", "ya pon la música"):
        assert not is_farewell(text), text


def test_goodbye_is_local_unless_it_carries_an_order():
    import asyncio
    from tests.test_one_request import brain, reply
    b, models = brain(reply("[happy] Listo, cerré Spotify. ¡Adiós!", ("close_app", {"name": "spotify"})))
    _, text, farewell = asyncio.run(b.chat("ya está, gracias"))
    assert farewell and not models.requests and text, "a plain goodbye costs no request"
    _, _, farewell = asyncio.run(b.chat("adiós, cierra spotify"))
    assert farewell and len(models.requests) == 1, "the order still goes to Gemini, then she hides"


if __name__ == "__main__":
    test_farewell()
    test_done_phrases_are_goodbyes_only_when_alone()
    test_goodbye_is_local_unless_it_carries_an_order()
    print("ok")
