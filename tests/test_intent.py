"""What a heard phrase is, checked against real transcriptions from the logs. A phrase that went wrong in a log gets
one line here, next to what it should have been.

Run: core\\.venv\\Scripts\\python.exe -m tests.test_intent  (or with pytest)
"""

from core.intent import classify, has_chained_orders, is_farewell, says_goodbye, starts_with_order

CUES = ("¿Sí?", "¿Dime?", "¿Mm?", "¿Qué pasa?", "¡Aquí estoy!")

# (heard, what it is). Plain phrases, no cue just said and no previous answer
TABLE = [
    # Whisper's YouTube outros in noise (log 24-oct: "¡Suscríbete!" reopened the last web page)
    ("¡Suscríbete!", "noise"),
    ("Subtítulos realizados por la comunidad de Amara.org", "noise"),
    ("", "noise"),
    # Thanks with a pet name: local, not a replayed order from Gemini (log 3-nov)
    ("Gracias mi amor.", "farewell"),
    ("Gracias guapa.", "farewell"),
    ("Mi amor, abre Spotify.", "order"),
    # Orders to hide, usted forms and Whisper's spellings (logs 26-oct, 27-oct, 1-nov)
    ("Ocúltate.", "hide"),
    ("Nada, nada. Cúltese.", "hide"),
    ("Miku, apaguece!", "hide"),
    ("Apángese Miku.", "hide"),
    ("Ya, Miku, vete", "hide"),
    ("ya puedes irte", "hide"),
    # "Turn yourself off" as Whisper writes it (log 2-nov: Gemini paused the music or asked to shut down the PC)
    ("Miku, ella. Apáquese.", "hide"),
    ("Apague ese, Miku.", "hide"),
    ("apágate un rato", "hide"),
    # Goodbyes in other words (log 27-oct: "Olvíalo, muchas gracias" kept her listening)
    ("Olvíalo, muchas gracias.", "farewell"),
    ("Ya está, gracias", "farewell"),
    ("Nada, nada.", "farewell"),
    ("Listo, eso era todo, gracias", "farewell"),
    ("No te necesito", "farewell"),
    ("Bueno, nos vemos mañana", "farewell"),
    # "Leave it there": the user does not want to go on (user, 3-nov)
    ("Eso es todo. Déjalo ahí.", "farewell"),
    ("Déjalo ahí", "farewell"),
    ("Mejor déjalo", "farewell"),
    ("Déjalo ahí nomás", "farewell"),
    ("Déjalo para mañana", "chat"),  # postpones something: Gemini answers
    # A goodbye word inside a question or an order is not a goodbye (audit 2-nov: she said bye instead of answering)
    ("¿Cómo se dice adiós en japonés?", "chat"),
    ("¿Eso es todo lo que sabes?", "chat"),
    ("¿Qué significa chao?", "chat"),
    ("nada más dime la hora", "chat"),
    ("ya terminé mis pendientes de hoy", "chat"),
    ("vete a youtube", "chat"),
    # A longer phrase ending in a goodbye: Gemini answers it, then she hides (log 2-nov: she stayed)
    ("Estás bien linda, mi amigo. Te amo. Ya eso es todo. Chau!", "chat"),
    # A goodbye with an order: the order first, then she hides
    ("adiós, cierra spotify", "order"),
    ("gracias, ahora abre spotify", "order"),
    ("Gracias, cierre Spotify", "order"),
    # Orders (log 27-oct: "Cierra me OBS Studio" after a quiet "Hey Miku"; log 1-nov: usted forms)
    ("Cierra me OBS Studio.", "order"),
    ("Póngale pausa y sérame todas las ventanas que están abiertas", "order"),
    ("Hey Miku, abre Spotify", "order"),
    # Chat: no tool, no goodbye
    ("¿ya está abierto spotify?", "chat"),  # a question, not "ya está" (Gemini answers it with the PC state)
    ("¿Cómo estás?", "chat"),
    ("¡Sí!", "chat"),  # in a conversation, the answer to her question (log 1-nov: dropped, she left)
    ("eso es", "chat"),
    ("Cuatro más, el mejor de cinco.", "chat"),
]


def test_table():
    wrong = [(text, want, classify(text)) for text, want in TABLE if classify(text) != want]
    assert not wrong, wrong


def test_her_own_voice_is_an_echo():
    # Her cue, only right after saying it
    for text in ("¿Sí?", "Sí.", "¿Dime?"):
        assert classify(text, cues=CUES) == "echo", text
    assert classify("Sí, abre Spotify", cues=CUES) == "order"
    # The tail of her last answer, when the mic opens right after she speaks
    assert classify("en YouTube", last_answer="¡Listo! Puse More en YouTube.") == "echo"
    assert classify("YouTube", last_answer="¡Listo! Puse More en YouTube.") != "echo", "one word is not enough"


def test_order_shapes():
    # The wake check: an order in the first words, by its stem
    for text in ("Cierra me OBS Studio.", "Miku, súbele al volumen", "Oye, pon música"):
        assert starts_with_order(text), text
    for text in ("y entonces ganamos la partida", "¡Granza de la..."):
        assert not starts_with_order(text), text
    # Several orders: Gemini does all of them, the fast path would do only one
    for text in ("abre Spotify y pon el volumen al 30", "Póngale pausa y sérame todas las ventanas",
                 "Dale play y sub el volumen al máximo."):  # it only raised Windows' volume, to 100% (log 4-nov)
        assert has_chained_orders(text), text
    for text in ("Hey Miku, abre Spotify", "pon el volumen al 30"):
        assert not has_chained_orders(text), text


def test_goodbyes_that_hide_her():
    # Said by the user: the last sentence counts, an order after a goodbye does not end it
    assert is_farewell("Estás bien linda, mi amigo. Te amo. Ya eso es todo. Chau!")
    assert is_farewell("Cierra Spotify. Gracias.")
    assert not is_farewell("Gracias. Ahora abre Spotify")
    assert not is_farewell("Abre la carpeta de descargas, por favor")
    # Said by her without the [adios] tag (log 2-nov: the mic stayed open after these)
    for answer in ("¡Hasta luego, que descanses!", "¡Entendido, mi amor! Me voy a dormir un rato.", "¡Nos vemos!",
                   "¡Vale! Aquí estaré si me necesitas."):
        assert says_goodbye(answer), answer
    for answer in ("Sayonara significa adiós en japonés.", "¡Aquí estoy! ¿Qué necesitas?", "¡Listo, ya lo pauso!",
                   "¡Buenas noches! ¿Qué necesitas antes de descansar?", "¡Claro! Me voy a acordar de eso."):
        assert not says_goodbye(answer), answer


if __name__ == "__main__":
    test_goodbyes_that_hide_her()
    test_table()
    test_her_own_voice_is_an_echo()
    test_order_shapes()
    print("ok")
