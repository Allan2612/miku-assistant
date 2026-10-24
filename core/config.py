"""Configuration loader and typed models for Miku Assistant."""

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Any, Optional
from dotenv import load_dotenv
import yaml

ROOT_DIR = Path(__file__).resolve().parent.parent


@dataclass(slots=True)
class WindowConfig:
    width: int = 400
    height: int = 600
    anchor: str = "bottom-right"
    margin: int = 16
    fps_visible: int = 30


@dataclass(slots=True)
class BehaviorConfig:
    hide_after_seconds: int = 20
    max_record_seconds: int = 15
    silence_ms: int = 800
    unload_after_minutes: int = 10


@dataclass(slots=True)
class LLMConfig:
    model: str = "gemini-3.5-flash-lite"
    models_fallback: list[str] = field(default_factory=list)  # empty: llm.DEFAULT_FALLBACKS
    max_history_turns: int = 10
    web_search: bool = False  # Google search inside the single request; the free tier rejects it (429)
    temperature: float = 0.8



@dataclass(slots=True)
class STTConfig:
    model: str = "small"
    device: str = "cpu"
    compute_type: str = "int8"
    cpu_threads: int = 4


@dataclass(slots=True)
class TTSConfig:
    voice: str = "es-ES-XimenaNeural"
    rate: str = "+0%"
    pitch: str = "+0Hz"



@dataclass(slots=True)
class RVCConfig:
    enabled: bool = True
    model: str = "models/rvc/miku.pth"
    index: str = "models/rvc/miku.index"
    f0_up_key: int = 0
    index_rate: float = 0.2


@dataclass(slots=True)
class WakewordConfig:
    enabled: bool = False
    model: str = "models/wakeword/hey_miku.onnx"
    threshold: float = 0.7
    patience: int = 2
    vad_threshold: float = 0.0


@dataclass(slots=True)
class Live2DConfig:
    model: str = "models/miku/miku.model3.json"
    scale: float = 0.25
    expressions: dict[str, Optional[str]] = field(default_factory=dict)


@dataclass(slots=True)
class ToolsConfig:
    confirm_destructive: bool = True
    file_search_roots: list[str] = field(default_factory=list)


@dataclass(slots=True)
class AppConfig:
    hotkey: str = "Ctrl+Alt+M"
    language: str = "es"
    log_level: str = "INFO"
    gemini_api_key: str = ""
    window: WindowConfig = field(default_factory=WindowConfig)
    behavior: BehaviorConfig = field(default_factory=BehaviorConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    stt: STTConfig = field(default_factory=STTConfig)
    tts: TTSConfig = field(default_factory=TTSConfig)
    rvc: RVCConfig = field(default_factory=RVCConfig)
    wakeword: WakewordConfig = field(default_factory=WakewordConfig)
    live2d: Live2DConfig = field(default_factory=Live2DConfig)
    tools: ToolsConfig = field(default_factory=ToolsConfig)
    apps: dict[str, str] = field(default_factory=dict)
    # name -> steps [{tool, args}], run locally by run_routine / "modo <name>"
    routines: dict[str, list[dict[str, Any]]] = field(default_factory=dict)


def load_config(
    config_path: Optional[Path | str] = None,
    env_path: Optional[Path | str] = None,
) -> AppConfig:
    """Load configuration from config.yaml and environment variables (.env)."""
    cfg_file = Path(config_path) if config_path else ROOT_DIR / "config.yaml"
    dotenv_file = Path(env_path) if env_path else ROOT_DIR / ".env"

    if dotenv_file.is_file():
        load_dotenv(dotenv_path=dotenv_file, override=False)
    else:
        load_dotenv(override=False)

    raw_data: dict[str, Any] = {}
    if cfg_file.is_file():
        with open(cfg_file, "r", encoding="utf-8") as f:
            loaded = yaml.safe_load(f)
            if isinstance(loaded, dict):
                raw_data = loaded

    # "or {}": an empty YAML section loads as None (H-033)
    window_data = raw_data.get("window") or {}
    behavior_data = raw_data.get("behavior") or {}
    llm_data = raw_data.get("llm") or {}
    stt_data = raw_data.get("stt") or {}
    tts_data = raw_data.get("tts") or {}
    rvc_data = raw_data.get("rvc") or {}
    wakeword_data = raw_data.get("wakeword") or {}
    live2d_data = raw_data.get("live2d") or {}
    tools_data = raw_data.get("tools") or {}
    apps_data = raw_data.get("apps") or {}

    return AppConfig(
        hotkey=raw_data.get("hotkey", "Ctrl+Alt+M"),
        language=raw_data.get("language", "es"),
        log_level=raw_data.get("log_level", "INFO").upper(),
        gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
        window=WindowConfig(
            width=window_data.get("width", 400),
            height=window_data.get("height", 600),
            anchor=window_data.get("anchor", "bottom-right"),
            margin=window_data.get("margin", 16),
            fps_visible=window_data.get("fps_visible", 30),
        ),
        behavior=BehaviorConfig(
            hide_after_seconds=behavior_data.get("hide_after_seconds", 20),
            max_record_seconds=behavior_data.get("max_record_seconds", 15),
            silence_ms=behavior_data.get("silence_ms", 800),
            unload_after_minutes=behavior_data.get("unload_after_minutes", 10),
        ),
        llm=LLMConfig(
            model=llm_data.get("model", "gemini-3.5-flash-lite"),
            models_fallback=list(llm_data.get("models_fallback") or []),
            max_history_turns=llm_data.get("max_history_turns", 10),
            temperature=float(llm_data.get("temperature", 0.8)),
            web_search=bool(llm_data.get("web_search", False)),
        ),

        stt=STTConfig(
            model=stt_data.get("model", "small"),
            device=stt_data.get("device", "cpu"),
            compute_type=stt_data.get("compute_type", "int8"),
            cpu_threads=int(stt_data.get("cpu_threads", 4)),
        ),
        tts=TTSConfig(
            voice=tts_data.get("voice", "es-ES-XimenaNeural"),
            rate=tts_data.get("rate", "+0%"),
            pitch=tts_data.get("pitch", "+0Hz"),
        ),

        rvc=RVCConfig(
            enabled=bool(rvc_data.get("enabled", True)),
            model=rvc_data.get("model", "models/rvc/miku.pth"),
            index=rvc_data.get("index", "models/rvc/miku.index"),
            f0_up_key=int(rvc_data.get("f0_up_key", 0)),
            index_rate=float(rvc_data.get("index_rate", 0.2)),
        ),
        wakeword=WakewordConfig(
            enabled=bool(wakeword_data.get("enabled", False)),
            model=wakeword_data.get("model", "models/wakeword/hey_miku.onnx"),
            threshold=float(wakeword_data.get("threshold", 0.7)),
            patience=int(wakeword_data.get("patience", 2)),
            vad_threshold=float(wakeword_data.get("vad_threshold", 0.0)),  # 0 = openWakeWord VAD off (previous behavior)
        ),
        live2d=Live2DConfig(
            model=live2d_data.get("model", "models/miku/miku.model3.json"),
            scale=float(live2d_data.get("scale", 0.25)),
            expressions=live2d_data.get("expressions", {}),
        ),
        tools=ToolsConfig(
            confirm_destructive=bool(tools_data.get("confirm_destructive", True)),
            file_search_roots=tools_data.get("file_search_roots", ["~/Desktop", "~/Documents", "~/Downloads"]),
        ),
        apps=dict(apps_data),
        routines={str(k).lower(): list(v or []) for k, v in (raw_data.get("routines") or {}).items()},
    )
