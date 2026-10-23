"""Phase 3 tools: memory, routines (0 requests via fast path), text files (no overwrite, Desktop only).

Memory and files use temp paths; routine steps are faked. Nothing touches the real PC.
Run: core\\.venv\\Scripts\\python.exe -m tests.test_phase3_tools  (or with pytest)
"""

import os
import tempfile
from pathlib import Path

os.environ.setdefault("GEMINI_API_KEY", "test")

import core.tools as tools
import core.tools.files as files
import core.tools.memory as memory
import core.tools.routines as routines
from core.llm import MikuBrain

tmp = Path(tempfile.mkdtemp())
memory.MEMORY_FILE = tmp / "memory.json"


def test_memory_remember_forget_and_prompt():
    assert memory.memory_facts() == []
    memory.remember("Le gusta  Frieren")
    memory.remember("le gusta frieren")  # same fact: no duplicate
    memory.remember("Su gato se llama Mochi")
    assert memory.memory_facts() == ["le gusta frieren", "Su gato se llama Mochi"]
    assert "- Su gato se llama Mochi" in MikuBrain._build_system_instruction(None)
    assert memory.forget("gato")["ok"] and memory.memory_facts() == ["le gusta frieren"]
    assert not memory.forget("perro")["ok"]
    memory.MEMORY_FILE.write_text("{broken", encoding="utf-8")
    assert memory.memory_facts() == [], "a broken file must not crash Miku"


def test_routine_runs_steps_locally_via_fast_path():
    ran = []
    tools._TOOL_METADATA["_fake_step"] = {"function": lambda **kw: ran.append(kw) or {"ok": True, "result": ""},
                                         "destructive": False}
    routines.ROUTINES["musica"] = [{"tool": "_fake_step", "args": {"level": 50}}, {"tool": "shutdown_pc"}]
    res = MikuBrain._try_fast_path_tool(None, "¡Activa el modo música!")
    assert ran == [{"level": 50}], ran
    assert res[0] == "sad" and "shutdown_pc" in res[1], "destructive steps are skipped, and reported"
    assert MikuBrain._try_fast_path_tool(None, "modo avión") is None, "unknown routine goes to Gemini"


def test_text_files_stay_on_desktop_and_never_overwrite():
    files.Path.home = staticmethod(lambda: tmp)
    (tmp / "Desktop").mkdir()
    assert files.create_text_file("../../evil", "x")["ok"]
    assert (tmp / "Desktop" / "evil.txt").read_text(encoding="utf-8") == "x", "path parts are dropped"
    res = files.create_text_file("evil.txt", "nuevo")
    assert not res["ok"] and (tmp / "Desktop" / "evil.txt").read_text(encoding="utf-8") == "x"

    files.DEFAULT_SEARCH_ROOTS = [tmp / "Desktop"]
    files.create_text_file("compras", "leche y pan")
    assert files.read_text_file("compras")["result"] == "compras.txt dice: leche y pan"


def test_read_notes_speaks_without_timestamps():
    import core.tools.notes as notes
    notes.NOTES_FILE = tmp / "notes.md"
    notes.NOTES_FILE.write_text("# Notas de Miku\n\n- [2026-10-20 02:58] comprar pan\n- [2026-10-23 14:14] subir el PR.\n",
                                encoding="utf-8")
    assert notes.read_notes()["result"] == "Tus últimas 2 notas: comprar pan. subir el PR."
    assert notes.read_notes(1)["result"] == "Tu última nota: subir el PR."


if __name__ == "__main__":
    test_read_notes_speaks_without_timestamps()
    test_memory_remember_forget_and_prompt()
    test_routine_runs_steps_locally_via_fast_path()
    test_text_files_stay_on_desktop_and_never_overwrite()
    print("ok")
