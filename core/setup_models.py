"""
Miku Assistant - Downloads, during the first start, what she would otherwise fetch on her first answer: Whisper's
model and, with the voice on, ContentVec (the base of the RVC voice). Run by installer/setup.ps1.

    python -m core.setup_models [--voice]
"""

import sys


def main() -> None:
    from core.config import load_config

    config = load_config()
    print(f"Whisper {config.stt.model}...", flush=True)
    from faster_whisper import WhisperModel

    WhisperModel(config.stt.model, device="cpu", compute_type="int8")
    if "--voice" in sys.argv:
        print("ContentVec...", flush=True)
        from huggingface_hub import snapshot_download

        snapshot_download("lengyue233/content-vec-best")
    print("ok", flush=True)


if __name__ == "__main__":
    main()
