import asyncio
import logging
import logging.handlers
import os
import signal
import sys
import threading
import time
from pathlib import Path

# Ensure project root is always in sys.path
root_dir = str(Path(__file__).resolve().parent.parent)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from .config import load_config
from .paths import CACHE
from .llm import MikuBrain
from .server import MikuServer
from .tts import TTSManager
from .stt import STTManager
from .rvc import RVCManager
from .audio_in import AudioInput
from .resources import ResourceManager
from .pipeline import MikuPipeline
from .wakeword import WakeWordListener
from .tools.timers import restore_timers

logger = logging.getLogger("miku.core")


PARENT_CHECK_S = 2.0
PARENT_GRACE_S = 10.0


def watch_parent(loop: asyncio.AbstractEventLoop, stop_event: asyncio.Event) -> None:
    """Started by miku.exe (MIKU_PARENT_PID): when it is gone (closed, crashed, killed by stop.bat), shut down instead
    of keeping the mic open. A thread, not a task: it must work even if the event loop is stuck."""
    raw = os.environ.get("MIKU_PARENT_PID")
    if not raw:
        return  # started by hand (start.bat of old, a test): nobody to watch
    import psutil

    try:
        parent = psutil.Process(int(raw))
    except (psutil.Error, ValueError):
        parent = None

    def run() -> None:
        while parent is not None and parent.is_running():  # is_running also checks it is not a reused PID
            time.sleep(PARENT_CHECK_S)
        logger.info("miku.exe is gone: shutting down.")
        loop.call_soon_threadsafe(stop_event.set)
        time.sleep(PARENT_GRACE_S)
        os._exit(0)  # the normal shutdown got stuck; the RVC worker exits on its own when its pipe closes

    threading.Thread(target=run, daemon=True, name="miku-parent-watch").start()


async def async_main() -> None:
    config = load_config()

    CACHE.mkdir(parents=True, exist_ok=True)
    # stop.bat kills exactly this process tree instead of matching command lines (H-053)
    pid_file = CACHE / "core.pid"
    pid_file.write_text(str(os.getpid()), encoding="ascii")
    handlers: list[logging.Handler] = [
        # Rotating: the log grew without limit (H-029)
        logging.handlers.RotatingFileHandler(
            CACHE / "core.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8"
        )
    ]
    if sys.stderr is not None:
        handlers.append(logging.StreamHandler(sys.stderr))

    numeric_level = getattr(logging, config.log_level, logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        # Milliseconds: activation latency (wake word -> cue -> mic) is invisible at 1 s resolution
        format="%(asctime)s.%(msecs)03d [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",  # the date: the panel's Logs separates days
        handlers=handlers,
    )

    api_key_status = "present" if config.gemini_api_key else "not set (check .env)"

    logger.info("==========================================")
    logger.info("         Miku Assistant Core Running      ")
    logger.info("==========================================")
    logger.info("Config loaded successfully:")
    logger.info("  - Language: %s | Hotkey: %s | Log Level: %s", config.language, config.hotkey, config.log_level)
    logger.info("  - Window: %dx%d (%d FPS)", config.window.width, config.window.height, config.window.fps_visible)
    logger.info("  - LLM Model: %s (fallbacks: %s, API key: %s)", config.llm.model, config.llm.models_fallback, api_key_status)
    logger.info("  - TTS Voice: %s (rate=%s, pitch=%s)", config.tts.voice, config.tts.rate, config.tts.pitch)
    logger.info("  - RVC Voice: enabled=%s, model=%s, f0_up_key=%d", config.rvc.enabled, config.rvc.model, config.rvc.f0_up_key)
    logger.info("  - WakeWord: enabled=%s, model=%s, threshold=%.2f", config.wakeword.enabled, config.wakeword.model, config.wakeword.threshold)
    logger.info("  - STT Engine: faster-whisper %s (device=%s, %s, %d threads)", config.stt.model, config.stt.device, config.stt.compute_type, config.stt.cpu_threads)
    logger.info("  - Inactivity unload timeout: %d min", config.behavior.unload_after_minutes)

    brain = MikuBrain(
        model_name=config.llm.model,
        models_fallback=config.llm.models_fallback,
        max_history=config.llm.max_history_turns,
        temperature=config.llm.temperature,
        web_search=config.llm.web_search,
        history_file=CACHE / "history.json",
    )

    tts = TTSManager(
        voice=config.tts.voice,
        rate=config.tts.rate,
        pitch=config.tts.pitch,
    )

    stt = STTManager(
        model_size=config.stt.model,
        device=config.stt.device,
        compute_type=config.stt.compute_type,
        cpu_threads=config.stt.cpu_threads,
        language=config.language,
        vocabulary=config.stt.vocabulary,
    )

    rvc = RVCManager(config=config.rvc)

    audio_in = AudioInput(sample_rate=16000, channels=1, device_name=config.audio.input_device)

    resources = ResourceManager(unload_after_minutes=config.behavior.unload_after_minutes)
    resources.register_rvc(rvc)
    resources.start()

    server = MikuServer(host="127.0.0.1", port=8765)

    pipeline = MikuPipeline(
        brain=brain,
        tts=tts,
        stt=stt,
        audio_in=audio_in,
        resources=resources,
        server=server,
        rvc=rvc,
        silence_ms=config.behavior.silence_ms,
        max_record_seconds=config.behavior.max_record_seconds,
        follow_up_s=config.behavior.follow_up_seconds,
        hide_after_s=config.behavior.hide_after_seconds,
        over_fullscreen=config.window.over_fullscreen,
    )
    server.set_pipeline(pipeline)
    restore_timers()  # after the pipeline registered itself as the timer notifier

    await server.start()

    logger.info("Miku Core is active and waiting for connections on ws://127.0.0.1:8765")

    stop_event = asyncio.Event()
    server.on_shutdown = stop_event.set
    watch_parent(asyncio.get_running_loop(), stop_event)

    def signal_handler():
        logger.info("Shutdown signal received.")
        stop_event.set()

    loop = asyncio.get_running_loop()

    wakeword = WakeWordListener(
        config=config.wakeword,
        on_wake=lambda clip: pipeline.handle_voice_activation(wake_clip=clip),
        loop=loop,
        device_name=config.audio.input_device,
    )
    pipeline.set_wakeword(wakeword)
    wakeword.start()

    # Pre-warm STT and RVC in background for instant first interaction
    background = {asyncio.create_task(stt.warmup())}  # keep refs so tasks are not collected
    if rvc.enabled:
        background.add(asyncio.create_task(rvc.warmup()))

    # Schedule once-per-day startup greeting according to current hour
    background.add(asyncio.create_task(pipeline.check_startup_greeting()))
    background.add(asyncio.create_task(pipeline.prepare_acks()))

    if sys.platform != "win32":
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, signal_handler)

    try:
        await stop_event.wait()
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    finally:
        logger.info("Shutting down Miku Core...")
        wakeword.stop()
        rvc.terminate_worker()
        await resources.stop()
        await server.stop()
        pid_file.unlink(missing_ok=True)


def main() -> None:
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        logger.info("Process interrupted by user. Exiting.")


if __name__ == "__main__":
    main()
