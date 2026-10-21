"""
Miku Assistant - Text to Speech (TTS) using edge-tts
Features async synthesis, on-disk caching (cache/voice/), and graceful degradation.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
from pathlib import Path
from typing import Optional, Tuple
import edge_tts

logger = logging.getLogger("miku.tts")

DEFAULT_CACHE_DIR = Path(__file__).resolve().parent.parent / "cache" / "voice"


class TTSManager:
    def __init__(
        self,
        voice: str = "es-MX-DaliaNeural",
        rate: str = "+5%",
        pitch: str = "+20Hz",
        cache_dir: Optional[Path] = None,
    ):
        self.voice = voice
        self.rate = rate
        self.pitch = pitch
        self.cache_dir = cache_dir or DEFAULT_CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_cache_path(self, text: str) -> Path:
        """Computes a unique MD5 hash based on text and voice settings."""
        key = f"{self.voice}:{self.rate}:{self.pitch}:{text.strip()}"
        md5_hash = hashlib.md5(key.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{md5_hash}.mp3"

    async def synthesize(self, text: str, cache: bool = False) -> Optional[Tuple[str, str]]:
        """
        Synthesizes speech for the given text.
        Returns (audio_b64, mime_type) or None if synthesis fails.
        Only fixed phrases should pass cache=True: LLM answers are almost never repeated,
        so caching them only grew cache/voice/ forever (H-040).
        """
        clean_text = text.strip()
        if not clean_text:
            return None

        cache_file = self._get_cache_path(clean_text)

        # 1. Check disk cache
        if cache_file.exists() and cache_file.stat().st_size > 0:
            try:
                audio_bytes = cache_file.read_bytes()
                logger.debug("TTS Cache HIT for '%s' (%d bytes)", clean_text[:30], len(audio_bytes))
                b64 = base64.b64encode(audio_bytes).decode("ascii")
                return b64, "audio/mpeg"
            except Exception as e:
                logger.warning("Failed reading cached audio file: %s", e)

        # 2. Call edge-tts asynchronously
        try:
            logger.info("Synthesizing speech via edge-tts (%s): '%s'", self.voice, clean_text[:40])
            communicate = edge_tts.Communicate(
                text=clean_text,
                voice=self.voice,
                rate=self.rate,
                pitch=self.pitch,
            )

            audio_data = bytearray()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data.extend(chunk["data"])

            if not audio_data:
                logger.warning("edge-tts returned empty audio data for: '%s'", clean_text)
                return None

            # 3. Write to disk cache (temp file + rename: a crash never leaves a truncated mp3)
            if cache:
                try:
                    tmp = cache_file.with_suffix(".tmp")
                    tmp.write_bytes(audio_data)
                    os.replace(tmp, cache_file)
                except Exception as e:
                    logger.warning("Could not cache synthesized audio: %s", e)

            b64 = base64.b64encode(audio_data).decode("ascii")
            return b64, "audio/mpeg"

        except Exception as e:
            logger.error("Error synthesizing speech with edge-tts: %s", e)
            return None

    async def prepopulate_cache(self, phrases: list[str]) -> None:
        """Pre-synthesizes fixed phrases into disk cache for instant playback."""
        for phrase in phrases:
            clean = phrase.strip()
            if not clean:
                continue
            cache_file = self._get_cache_path(clean)
            if not cache_file.exists():
                logger.info("Pre-caching fixed voice phrase: '%s'", clean)
                await self.synthesize(clean, cache=True)
