import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

# Ensure project root is always in sys.path
root_dir = str(Path(__file__).resolve().parent.parent)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from .config import load_config
from .llm import MikuBrain
from .server import MikuServer
from .tts import TTSManager
from .stt import STTManager
from .rvc import RVCManager
from .audio_in import AudioInput
from .resources import ResourceManager
from .pipeline import MikuPipeline
from .wakeword import WakeWordListener

logger = logging.getLogger("miku.core")


async def async_main() -> None:
    config = load_config()

    os.makedirs("cache", exist_ok=True)
    handlers: list[logging.Handler] = [
        logging.FileHandler("cache/core.log", mode="a", encoding="utf-8")
    ]
    if sys.stderr is not None:
        handlers.append(logging.StreamHandler(sys.stderr))

    numeric_level = getattr(logging, config.log_level, logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
    )

    api_key_status = "present" if config.gemini_api_key else "not set (check .env)"

    logger.info("==========================================")
    logger.info("  Miku Assistant Core - Phase 7 Running   ")
    logger.info("==========================================")
    logger.info("Config loaded successfully:")
    logger.info("  - Language: %s | Hotkey: %s | Log Level: %s", config.language, config.hotkey, config.log_level)
    logger.info("  - Window: %dx%d (%s, %d FPS)", config.window.width, config.window.height, config.window.anchor, config.window.fps_visible)
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
    )

    rvc = RVCManager(config=config.rvc)

    audio_in = AudioInput(sample_rate=16000, channels=1)

    resources = ResourceManager(unload_after_minutes=config.behavior.unload_after_minutes)
    resources.register_stt(stt)
    resources.register_rvc(rvc)
    resources.start()

    server = MikuServer(host="127.0.0.1", port=8765, brain=brain, tts=tts)

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
    )
    server.set_pipeline(pipeline)

    await server.start()

    logger.info("Miku Core is active and waiting for connections on ws://127.0.0.1:8765")

    stop_event = asyncio.Event()
    server.on_shutdown = stop_event.set

    def signal_handler():
        logger.info("Shutdown signal received.")
        stop_event.set()

    loop = asyncio.get_running_loop()

    wakeword = WakeWordListener(
        config=config.wakeword,
        on_wake=pipeline.handle_voice_activation,
        loop=loop,
    )
    pipeline.set_wakeword(wakeword)
    wakeword.start()

    # Pre-warm STT and RVC in background for instant first interaction
    asyncio.create_task(stt.warmup())
    if rvc.enabled:
        asyncio.create_task(rvc.warmup())

    # Schedule once-per-day startup greeting according to current hour
    asyncio.create_task(pipeline.check_startup_greeting())

    if sys.platform != "win32":
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, signal_handler)

    try:
        while not stop_event.is_set():
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                pass
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    finally:
        logger.info("Shutting down Miku Core...")
        wakeword.stop()
        rvc.terminate_worker()
        await resources.stop()
        await server.stop()


def main() -> None:
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        logger.info("Process interrupted by user. Exiting.")


if __name__ == "__main__":
    main()
