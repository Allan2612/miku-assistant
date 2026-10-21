"""
Miku Assistant - Tools Registry and Manager
Strict adherence to GEMINI.md:
- Closed list of PC control functions.
- Destructive tools only run after the USER confirms (H-001), never on the LLM's word.
- Graceful error isolation (returns dict {"ok": bool, "result": str}).
"""

import functools
import inspect
import logging
import re
import time
from typing import Callable, Dict, List, Any, Optional

logger = logging.getLogger("miku.tools")

_TOOL_REGISTRY: Dict[str, Callable] = {}
_TOOL_METADATA: Dict[str, Dict[str, Any]] = {}

# Destructive call waiting for the user's "sí": {"name", "kwargs", "time"}
_pending_confirmation: Optional[Dict[str, Any]] = None
# Set by note_user_reply() when the user said yes; consumed by the next call of that tool
_user_confirmed: Optional[Dict[str, Any]] = None
_CONFIRM_WINDOW_S = 60.0
_YES_WORDS = {"sí", "si", "confirmo", "adelante", "hazlo", "claro", "dale", "vale", "ok", "okay", "afirmativo", "correcto"}
_NO_WORDS = {"no", "cancela", "cancelar", "espera", "nada"}


def note_user_reply(text: str) -> None:
    """Called with every user message before the LLM sees it: a short 'sí' confirms the pending action."""
    global _pending_confirmation, _user_confirmed
    pending, _pending_confirmation = _pending_confirmation, None
    _user_confirmed = None
    if not pending or time.monotonic() - pending["time"] > _CONFIRM_WINDOW_S:
        return
    words = set(re.findall(r"\w+", text.lower()))
    if words & _YES_WORDS and not words & _NO_WORDS and len(words) <= 6:
        _user_confirmed = pending
        logger.info("User confirmed pending destructive tool [%s].", pending["name"])


def _short(value: Any) -> str:
    s = repr(value)
    return s if len(s) <= 120 else s[:117] + "..."


def tool(name: Optional[str] = None, description: Optional[str] = None, destructive: bool = False):
    """Decorator to register a PC control tool for Gemini."""
    def decorator(func: Callable):
        tool_name = name or func.__name__
        tool_desc = description or inspect.getdoc(func) or f"Herramienta {tool_name}"
        assert tool_name not in _TOOL_REGISTRY, f"duplicate tool name: {tool_name}"
        takes_confirmed = "confirmed" in inspect.signature(func).parameters

        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Dict[str, Any]:
            global _pending_confirmation, _user_confirmed
            if destructive:
                kwargs.pop("confirmed", None)  # the LLM cannot confirm on the user's behalf
                confirmed = _user_confirmed
                if confirmed and confirmed["name"] == tool_name:
                    _user_confirmed = None
                    args, kwargs = (), dict(confirmed["kwargs"])  # run exactly what the user approved
                    if takes_confirmed:
                        kwargs["confirmed"] = True
                else:
                    _pending_confirmation = {"name": tool_name, "kwargs": dict(kwargs), "time": time.monotonic()}
                    question = func(**kwargs, confirmed=False) if takes_confirmed else None
                    if not (isinstance(question, dict) and question.get("requires_confirmation")):
                        question = {"ok": False, "requires_confirmation": True,
                                    "result": f"¿Seguro que quieres que ejecute {tool_name}? Confirma diciendo sí."}
                    return question

            start_t = time.perf_counter()
            logger.info("Executing tool [%s] args=%s kwargs=%s", tool_name, _short(args), _short(kwargs))
            try:
                res = func(*args, **kwargs)
                logger.info("Tool [%s] succeeded in %.3fs: %s", tool_name, time.perf_counter() - start_t, _short(res))
                if isinstance(res, dict) and "ok" in res and "result" in res:
                    return res
                return {"ok": True, "result": str(res)}
            except Exception as e:
                logger.error("Tool [%s] failed after %.3fs: %s", tool_name, time.perf_counter() - start_t, e, exc_info=True)
                return {"ok": False, "result": f"Error al ejecutar {tool_name}: {e}"}

        wrapper.__name__ = tool_name
        wrapper.__doc__ = tool_desc

        _TOOL_REGISTRY[tool_name] = wrapper
        _TOOL_METADATA[tool_name] = {
            "name": tool_name,
            "description": tool_desc,
            "destructive": destructive,
            "function": wrapper,
        }
        return wrapper
    return decorator


def get_registered_tools() -> List[Callable]:
    """Returns a list of all registered tool functions for Gemini."""
    return list(_TOOL_REGISTRY.values())


def get_tool_metadata(name: str) -> Optional[Dict[str, Any]]:
    """Returns metadata for a specific tool."""
    return _TOOL_METADATA.get(name)


# Import all tool modules so decorators register them
import core.tools.apps
import core.tools.media
import core.tools.web
import core.tools.system
import core.tools.files
import core.tools.timers
import core.tools.notes
