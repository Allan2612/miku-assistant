"""
Miku Assistant - Tools Registry and Manager
Strict adherence to GEMINI.md:
- Closed list of PC control functions.
- Timeout of 5s per tool execution.
- Graceful error isolation (returns dict {"ok": bool, "result": str}).
"""

import functools
import inspect
import logging
import time
from typing import Callable, Dict, List, Any, Optional

logger = logging.getLogger("miku.tools")

_TOOL_REGISTRY: Dict[str, Callable] = {}
_TOOL_METADATA: Dict[str, Dict[str, Any]] = {}


def tool(name: Optional[str] = None, description: Optional[str] = None, destructive: bool = False):
    """Decorator to register a PC control tool for Gemini."""
    def decorator(func: Callable):
        tool_name = name or func.__name__
        tool_desc = description or inspect.getdoc(func) or f"Herramienta {tool_name}"

        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Dict[str, Any]:
            print(f"\n>>>> [TOOL TRIGGERED] {tool_name} with args={args}, kwargs={kwargs}")
            start_t = time.perf_counter()
            logger.info("Executing tool [%s] with args=%s, kwargs=%s", tool_name, args, kwargs)
            try:
                res = func(*args, **kwargs)
                elapsed = time.perf_counter() - start_t
                print(f">>>> [TOOL RESULT] {tool_name}: {res}")
                logger.info("Tool [%s] succeeded in %.3fs: %s", tool_name, elapsed, res)
                if isinstance(res, dict) and "ok" in res and "result" in res:
                    return res
                return {"ok": True, "result": str(res)}
            except Exception as e:
                elapsed = time.perf_counter() - start_t
                print(f">>>> [TOOL ERROR] {tool_name}: {e}")
                logger.error("Tool [%s] failed after %.3fs: %s", tool_name, elapsed, e, exc_info=True)
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
