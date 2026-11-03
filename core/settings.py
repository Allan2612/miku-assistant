"""
Miku Assistant - The panel's settings: read and write config.yaml and .env without losing their comments.

Run by miku.exe as a short process, so it works with Miku off:
    python -m core.settings get           -> JSON on stdout (secrets never in full: only whether they are set)
    python -m core.settings set < JSON    -> {"ok": true} or {"ok": false, "error": "..."}
    python -m core.settings tools         -> the tools, for the Herramientas page
    python -m core.settings testkey < KEY -> whether a Gemini API key works (empty: the saved one)

config.yaml is written by editing one value inside its section's braces (PyYAML would drop every comment), then
read back with load_config to check it; the previous file stays as config.yaml.bak.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

from core.paths import CONFIG, ENV

MODELS = ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3-flash-preview", "gemini-3.5-flash",
          "gemini-3.8-flash"]
# Tools that local phrases run without Gemini (the fast path in core/llm.py)
LOCAL_TOOLS = {"set_volume", "change_volume", "mute", "media_control", "youtube_player", "lock_pc", "list_timers",
               "set_timer", "remember", "take_note", "read_notes", "my_day", "quota_status", "obs", "weather",
               "watch_downloads", "show_desktop", "shutdown_pc", "run_routine", "get_datetime"}


def _literal(value: Any) -> str:
    """A YAML flow value: true/false, a number, a double-quoted string or a list of strings."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, list):
        return "[" + ", ".join(_literal(str(v)) for v in value) + "]"
    return json.dumps(str(value), ensure_ascii=False)  # JSON strings are valid YAML double-quoted strings


def _section_span(text: str, section: str) -> tuple[int, int]:
    """Start and end (the closing brace) of `section: { ... }`, which may span lines."""
    m = re.search(rf"^{re.escape(section)}:\s*\{{", text, re.MULTILINE)
    if not m:
        raise KeyError(f"No encuentro la sección {section} en config.yaml")
    depth, i = 1, m.end()
    in_str = False
    while i < len(text) and depth:
        c = text[i]
        if c == '"' and text[i - 1] != "\\":
            in_str = not in_str
        elif not in_str and c == "{":
            depth += 1
        elif not in_str and c == "}":
            depth -= 1
        i += 1
    return m.end(), i - 1


def set_value(text: str, section: str, key: str, value: Any) -> str:
    """config.yaml text with section.key = value (or the top-level key when section is "")."""
    lit = _literal(value)
    if not section:
        new, n = re.subn(rf'^({re.escape(key)}:\s*)("(?:[^"\\]|\\.)*"|[^\s#]+)', lambda m: m.group(1) + lit, text,
                         count=1, flags=re.MULTILINE)
        if not n:
            raise KeyError(f"No encuentro {key} en config.yaml")
        return new
    start, end = _section_span(text, section)
    body = text[start:end]
    pattern = rf'(?<![\w.])({re.escape(key)}:\s*)("(?:[^"\\]|\\.)*"|\[[^\]]*\]|[^,}}\n#]+?)(\s*[,}}\n]|\s*$)'
    new_body, n = re.subn(pattern, lambda m: m.group(1) + lit + m.group(3), body, count=1)
    if not n:  # not in the section yet: add it before the closing brace
        new_body = body.rstrip() + f", {key}: {lit} "
    return text[:start] + new_body + text[end:]


def _env_get(name: str) -> str:
    if ENV.is_file():
        for line in ENV.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith(f"{name}="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def _env_set(name: str, value: str) -> None:
    lines = ENV.read_text(encoding="utf-8").splitlines() if ENV.is_file() else []
    lines = [l for l in lines if not l.strip().startswith(f"{name}=")] + [f"{name}={value}"]
    tmp = ENV.with_suffix(".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tmp.replace(ENV)


def get() -> Dict[str, Any]:
    from core.config import load_config

    c = load_config(CONFIG, ENV)
    key = _env_get("GEMINI_API_KEY")
    return {
        "gemini": {"has_key": bool(key), "hint": key[-4:] if len(key) > 8 else "", "model": c.llm.model, "models": MODELS},
        "rvc_enabled": c.rvc.enabled,
        "wakeword_enabled": c.wakeword.enabled,
        "threshold": c.wakeword.threshold,
        "hotkey": c.hotkey,
        "weather_city": c.tools.weather_city,
        "vocabulary": [w.strip() for w in c.stt.vocabulary.rstrip(".").split(",") if w.strip()],
        "obs": {"has_password": bool(_env_get("OBS_PASSWORD"))},
        "disabled_tools": list(c.tools.disabled),
        "input_device": c.audio.input_device,
    }


def inputs() -> List[str]:
    """The microphones the panel offers (a separate call: listing them asks Windows for its devices)."""
    from core.audio_in import list_inputs

    return list_inputs()


def _validate(ch: Dict[str, Any]) -> List[str]:
    errors = []
    if "model" in ch and ch["model"] not in MODELS:
        errors.append("Modelo desconocido.")
    if "threshold" in ch and not (isinstance(ch["threshold"], (int, float)) and 0.1 <= ch["threshold"] <= 0.95):
        errors.append("El umbral va de 0,10 a 0,95.")
    for flag in ("rvc_enabled", "wakeword_enabled"):
        if flag in ch and not isinstance(ch[flag], bool):
            errors.append(f"{flag} debe ser sí o no.")
    if "weather_city" in ch and not (isinstance(ch["weather_city"], str) and 1 < len(ch["weather_city"]) <= 80):
        errors.append("La ciudad debe tener entre 2 y 80 caracteres.")
    if "vocabulary" in ch and not (isinstance(ch["vocabulary"], list) and len(ch["vocabulary"]) <= 60
                                  and all(isinstance(w, str) and 0 < len(w) <= 40 and "\n" not in w for w in ch["vocabulary"])):
        errors.append("Palabras de Whisper: hasta 60, de hasta 40 caracteres.")
    # "Ctrl+Alt+M": modifiers, then one key (letter, digit, F1-F24, Space)
    if "hotkey" in ch and not (isinstance(ch["hotkey"], str) and re.fullmatch(
            r"(?i)((ctrl|alt|shift|super)\+){1,3}([a-z0-9]|f([1-9]|1[0-9]|2[0-4])|space)", ch["hotkey"])):
        errors.append("Atajo no válido: una o más teclas Ctrl, Alt, Shift y una letra, número o F1-F24 (ej: Ctrl+Alt+M).")
    if "input_device" in ch and not (isinstance(ch["input_device"], str) and len(ch["input_device"]) <= 120):
        errors.append("Micrófono no válido.")
    if "disabled_tools" in ch and not (isinstance(ch["disabled_tools"], list) and all(isinstance(t, str) for t in ch["disabled_tools"])):
        errors.append("Lista de herramientas no válida.")
    for secret in ("api_key", "obs_password"):
        if secret in ch and not (isinstance(ch[secret], str) and 0 < len(ch[secret]) <= 200 and "\n" not in ch[secret]):
            errors.append("Contraseña o clave no válida.")
    return errors


def set_(ch: Dict[str, Any]) -> Dict[str, Any]:
    from core.config import load_config

    errors = _validate(ch)
    if errors:
        return {"ok": False, "error": " ".join(errors)}
    text = CONFIG.read_text(encoding="utf-8")
    edits = {"model": ("llm", "model"), "rvc_enabled": ("rvc", "enabled"), "wakeword_enabled": ("wakeword", "enabled"),
             "threshold": ("wakeword", "threshold"), "weather_city": ("tools", "weather_city"),
             "disabled_tools": ("tools", "disabled"), "hotkey": ("", "hotkey"), "input_device": ("audio", "input_device")}
    for field, (section, key) in edits.items():
        if field in ch:
            text = set_value(text, section, key, ch[field])
    if "vocabulary" in ch:
        text = set_value(text, "stt", "vocabulary", ", ".join(ch["vocabulary"]) + ".")
    # Read it back before keeping it: a broken config.yaml would stop Miku from starting
    tmp = CONFIG.with_suffix(".check.yaml")
    tmp.write_text(text, encoding="utf-8")
    try:
        c = load_config(tmp, ENV)
        expected = {"model": c.llm.model, "rvc_enabled": c.rvc.enabled, "wakeword_enabled": c.wakeword.enabled,
                    "threshold": c.wakeword.threshold, "weather_city": c.tools.weather_city,
                    "disabled_tools": list(c.tools.disabled), "hotkey": c.hotkey,
                    "input_device": c.audio.input_device}
        wrong = [f for f, v in expected.items() if f in ch and ch[f] != v]
        if wrong:
            return {"ok": False, "error": f"No se guardó bien: {', '.join(wrong)}. config.yaml no se tocó."}
    except Exception as e:  # anything load_config raises means the edit broke the file
        return {"ok": False, "error": f"config.yaml quedaría roto ({e}). No se tocó."}
    finally:
        tmp.unlink(missing_ok=True)
    CONFIG.with_suffix(".yaml.bak").write_text(CONFIG.read_text(encoding="utf-8"), encoding="utf-8")
    CONFIG.write_text(text, encoding="utf-8")
    if ch.get("api_key"):
        _env_set("GEMINI_API_KEY", ch["api_key"])
    if ch.get("obs_password"):
        _env_set("OBS_PASSWORD", ch["obs_password"])
    return {"ok": True}


def tools() -> List[Dict[str, Any]]:
    import os
    os.environ.setdefault("GEMINI_API_KEY", "")
    from core.tools import _TOOL_METADATA

    return [{"name": n, "description": m["description"], "destructive": m["destructive"], "local": n in LOCAL_TOOLS}
            for n, m in sorted(_TOOL_METADATA.items())]


def test_key(key: str) -> Dict[str, Any]:
    """Asks Gemini for the model's details: proves the key works without spending generation quota."""
    from google import genai
    from google.genai import types

    key = key.strip() or _env_get("GEMINI_API_KEY")
    if not key:
        return {"ok": False, "error": "No hay API key."}
    try:
        client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=8000))
        client.models.get(model=get()["gemini"]["model"])
        return {"ok": True}
    except Exception as e:
        msg = str(e)
        return {"ok": False, "error": "La API key no es válida." if any(t in msg for t in ("API_KEY", "401", "403", "PERMISSION"))
                else f"No pude comprobarla: {msg[:120]}"}


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "get":
        out: Any = get()
    elif cmd == "set":
        out = set_(json.loads(sys.stdin.read() or "{}"))
    elif cmd == "tools":
        out = tools()
    elif cmd == "inputs":
        out = inputs()
    elif cmd == "testkey":
        out = test_key(sys.stdin.read())
    else:
        out = {"ok": False, "error": "uso: get | set | tools | inputs | testkey"}
    sys.stdout.write(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
