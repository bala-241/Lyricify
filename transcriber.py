# =============================================================================
# app/transcriber.py — Speech-to-Text via OpenAI Whisper
# =============================================================================
# Responsibilities:
#   • Load the Whisper model once and cache it for the process lifetime
#   • Transcribe a vocals WAV file into structured text + metadata
#   • Expose language detection and timestamped segments for downstream use
#
# Pipeline position:
#   vocal_separator.py  →  transcriber.py  →  text_cleaner.py
#
# Library:
#   openai-whisper  → whisper.load_model / model.transcribe
# =============================================================================

# 1. IMPORTS
# =============================================================================
import logging
from pathlib import Path
from typing import Any

from app import config

# =============================================================================
# 2. MODULE LOGGER
# =============================================================================

logger = logging.getLogger(__name__)

# =============================================================================
# 3. GLOBAL MODEL CACHE
# =============================================================================

# Whisper models range from ~150 MB ("tiny") to ~3 GB ("large").
# We store the loaded model here so load_model() is free on every call
# after the first one.
_model = None

# =============================================================================
# 4. MODEL LOADER
# =============================================================================

def load_model():
    """
    Return a cached Whisper model instance.

    The model is loaded from disk on the **first call only**.  Every
    subsequent call returns the already-loaded object immediately (O(1)).

    Model size and compute device are both read from ``config``:

    * ``config.WHISPER_MODEL_SIZE``  — "tiny" | "base" | "small" |
                                       "medium" | "large"
    * ``config.DEVICE``              — "cpu" | "cuda"

    Returns
    -------
    whisper.Whisper
        A ready-to-use Whisper model.

    Raises
    ------
    RuntimeError
        If ``openai-whisper`` is not installed, or if the model cannot
        be downloaded / loaded.
    """
    global _model

    if _model is not None:
        logger.debug(
            "Whisper model '%s' already loaded — reusing cached instance.",
            config.WHISPER_MODEL_SIZE,
        )
        return _model

    logger.info(
        "Loading Whisper model '%s' on device '%s' …",
        config.WHISPER_MODEL_SIZE,
        config.DEVICE,
    )

    try:
        import whisper  # deferred: module usable even without whisper installed

        _model = whisper.load_model(
            config.WHISPER_MODEL_SIZE,
            device=config.DEVICE,
        )
        logger.info(
            "Whisper model '%s' loaded successfully.", config.WHISPER_MODEL_SIZE
        )
        return _model

    except ImportError as exc:
        raise RuntimeError(
            "openai-whisper is not installed. "
            "Run: pip install openai-whisper"
        ) from exc

    except Exception as exc:
        raise RuntimeError(
            f"Failed to load Whisper model '{config.WHISPER_MODEL_SIZE}': {exc}"
        ) from exc


# =============================================================================
# 5. TRANSCRIPTION
# =============================================================================

def transcribe_audio(audio_path: str) -> dict[str, Any]:
    """
    Transcribe *audio_path* (vocals WAV) to text using Whisper.

    Returns a structured dictionary so every downstream component can pick
    exactly what it needs without re-running transcription.

    Parameters
    ----------
    audio_path : str
        Path to the vocals WAV produced by ``vocal_separator.separate_vocals``.
        Must be a mono 16 kHz WAV for best results (handled by the pipeline).

    Returns
    -------
    dict with the following keys
    ──────────────────────────────
    text : str
        Full transcript as a single string (whitespace-stripped).
    segments : list[dict]
        List of timed segments, each containing:

        .. code-block:: python

            {
                "id":    0,
                "start": 0.0,   # seconds
                "end":   3.5,   # seconds
                "text":  "Hello world",
            }

        Useful for karaoke display, subtitle export, and quality review.
    language : str
        ISO 639-1 language code auto-detected by Whisper (e.g. ``"en"``).
    word_count : int
        Number of words in the full transcript.
    segment_count : int
        Number of timestamped segments returned by Whisper.
    model_size : str
        Which Whisper model was used (mirrors ``config.WHISPER_MODEL_SIZE``).

    Raises
    ------
    FileNotFoundError
        If *audio_path* does not exist on disk.
    ValueError
        If Whisper returns an empty transcript.
    RuntimeError
        If the model fails to load or transcription raises an unexpected error.

    Example
    -------
    >>> result = transcribe_audio("data/temp/song_normalized/vocals.wav")
    >>> print(result["text"])
    "Never gonna give you up, never gonna let you down …"
    >>> for seg in result["segments"]:
    ...     print(f"[{seg['start']:.1f}s – {seg['end']:.1f}s]  {seg['text']}")
    """
    # ── 1. Validate input ─────────────────────────────────────────────────────
    path = Path(audio_path)

    if not path.exists():
        raise FileNotFoundError(
            f"Vocals file not found: '{path}'. "
            "Ensure vocal_separator.separate_vocals() has run first."
        )

    logger.info("━━━  Transcription started  ━━━")
    logger.info("Input : %s", path)

    # ── 2. Load (or reuse) model ──────────────────────────────────────────────
    model = load_model()

    # ── 3. Run transcription ──────────────────────────────────────────────────
    logger.info("Transcribing audio …")

    try:
        raw = model.transcribe(
            str(path),
            fp16=config.USE_GPU,    # fp16 only safe on CUDA; False on CPU
            verbose=False,          # suppress per-segment stdout noise
        )
    except Exception as exc:
        raise RuntimeError(
            f"Whisper transcription failed for '{path}': {exc}"
        ) from exc

    # ── 4. Extract & validate results ─────────────────────────────────────────
    full_text = raw.get("text", "").strip()
    language  = raw.get("language", "unknown")
    segments  = raw.get("segments", [])

    logger.info("Detected language : %s", language)
    logger.debug("Raw segment count : %d", len(segments))

    # Empty-output guard
    if not full_text:
        # Noisy or instrumental tracks may produce nothing — treat as an error
        # so the caller knows the result is unusable rather than silently
        # returning empty data.
        raise ValueError(
            f"Whisper returned an empty transcript for '{path}'. "
            "The audio may be too noisy, silent, or entirely instrumental."
        )

    # ── 5. Clean & slim down segments ────────────────────────────────────────
    # Whisper segments carry many internal fields (tokens, temperature, etc.)
    # We keep only the fields useful to downstream modules.
    clean_segments = [
        {
            "id":    seg.get("id"),
            "start": round(seg.get("start", 0.0), 3),
            "end":   round(seg.get("end",   0.0), 3),
            "text":  seg.get("text", "").strip(),
        }
        for seg in segments
        if seg.get("text", "").strip()   # skip empty / noise-only segments
    ]

    # ── 6. Build structured result ────────────────────────────────────────────
    result: dict[str, Any] = {
        "text":          full_text,
        "segments":      clean_segments,
        "language":      language,
        "word_count":    len(full_text.split()),
        "segment_count": len(clean_segments),
        "model_size":    config.WHISPER_MODEL_SIZE,
    }

    logger.info(
        "Transcription complete — %d word(s) across %d segment(s).",
        result["word_count"],
        result["segment_count"],
    )
    logger.info("━━━  Transcription done  ━━━")

    return result


# =============================================================================
# 6. ACCESSOR FOR TESTS / RESET
# =============================================================================

def reset_model() -> None:
    """
    Clear the cached Whisper model.

    Intended for **testing only** — forces :func:`load_model` to reload the
    model on the next call.  Not used in the normal pipeline.
    """
    global _model
    _model = None
    logger.debug("Whisper model cache cleared.")


# =============================================================================
# QUICK SANITY-CHECK  (python app/transcriber.py)
# =============================================================================
if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(levelname)-8s │ %(name)s │ %(message)s",
    )

    # ── Edge case: missing file ───────────────────────────────────────────────
    print("=== Edge case: missing input file ===")
    try:
        transcribe_audio("nonexistent_vocals.wav")
    except FileNotFoundError as e:
        print(f"FileNotFoundError (OK) → {e}\n")

    # ── Full run on a real file if provided ───────────────────────────────────
    if len(sys.argv) > 1:
        audio_path = sys.argv[1]
        print(f"=== Transcribing: {audio_path} ===\n")
        result = transcribe_audio(audio_path)

        print(f"Language     : {result['language']}")
        print(f"Word count   : {result['word_count']}")
        print(f"Segments     : {result['segment_count']}")
        print(f"\nFull text:\n{result['text']}\n")
        print("First 3 segments:")
        for seg in result["segments"][:3]:
            print(f"  [{seg['start']:.2f}s – {seg['end']:.2f}s]  {seg['text']}")
        print("\n✅  Transcription complete.")
    else:
        print("Tip: pass a vocals WAV path to test the full pipeline:")
        print("     python transcriber.py data/temp/song_normalized/vocals.wav")
        print("\n✅  transcriber self-check complete (no real audio used).")