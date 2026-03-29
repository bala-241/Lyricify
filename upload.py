# =============================================================================
# app/upload.py — Pipeline Controller / Backend API Layer
# =============================================================================
# Responsibilities:
#   • Accept an uploaded file (Streamlit UploadedFile or CLI path)
#   • Orchestrate every pipeline stage in the correct order
#   • Return a single, structured response dict — success or failure
#   • Never crash the caller; all exceptions are caught and normalised
#
# Pipeline:
#   save_file()  →  process_audio()  →  separate_vocals()
#                →  transcribe_audio()  →  process_text()  →  return result
#
# In a web-API context this function maps 1-to-1 onto a POST /upload endpoint.
# =============================================================================

# 1. IMPORTS
# =============================================================================
import logging
import time
from pathlib import Path
from typing import Any

from app.utils.file_handler      import save_file, cleanup_temp_files
from app.services.audio_processor   import process_audio
from app.services.vocal_seperator   import separate_vocals
from app.services.transcriber       import transcribe_audio
from app.services.text_cleaner      import process_text
from app import config

# =============================================================================
# 2. MODULE LOGGER
# =============================================================================

logger = logging.getLogger(__name__)

# =============================================================================
# 3. RESPONSE BUILDERS  (private helpers)
# =============================================================================

def _success(data: dict[str, Any], steps: list[str], elapsed: float) -> dict[str, Any]:
    """Build a standardised success response."""
    return {
        "success":         True,
        "data":            data,
        "steps_completed": steps,
        "processing_time": round(elapsed, 2),
        "error":           None,
    }


def _failure(
    error: Exception | str,
    steps: list[str],
    elapsed: float,
    stage: str = "unknown",
) -> dict[str, Any]:
    """Build a standardised failure response."""
    message = str(error)
    logger.error("Pipeline failed at stage '%s': %s", stage, message)
    return {
        "success":         False,
        "data":            None,
        "steps_completed": steps,
        "processing_time": round(elapsed, 2),
        "error": {
            "stage":   stage,
            "message": message,
        },
    }


# =============================================================================
# 4. MAIN PIPELINE FUNCTION
# =============================================================================

def process_upload(uploaded_file) -> dict[str, Any]:
    """
    Run the complete lyrics-extraction pipeline on *uploaded_file*.

    Stages
    ------
    1. **save**        — Validate + persist the file via ``file_handler``
    2. **audio**       — Convert / resample / normalise via ``audio_processor``
    3. **separation**  — Extract vocals via ``vocal_separator`` (Spleeter)
    4. **transcription** — Speech → text via ``transcriber`` (Whisper)
    5. **cleaning**    — Post-process text via ``text_cleaner``

    Parameters
    ----------
    uploaded_file : UploadedFile | str | Path
        Accepts:

        * **Streamlit** ``UploadedFile`` (has ``.name``, ``.size``, ``.read()``)
        * **str / Path** pointing to an existing audio file (CLI / tests)

    Returns
    -------
    dict — always returned, never raises
    ─────────────────────────────────────
    On success::

        {
            "success": True,
            "data": {
                "lyrics":        str,   # formatted, line-broken lyrics
                "cleaned_text":  str,   # single-string cleaned transcript
                "original_text": str,   # raw Whisper output
                "segments":      list,  # timed lyric segments
                "language":      str,   # ISO 639-1 detected language
                "word_count":    int,
                "segment_count": int,
                "model_size":    str,
                "source_file":   str,   # saved input path
            },
            "steps_completed": ["file_saved", "audio_processed", ...],
            "processing_time": 14.37,
            "error": None,
        }

    On failure::

        {
            "success": False,
            "data":    None,
            "steps_completed": ["file_saved"],   # steps that DID complete
            "processing_time": 2.11,
            "error": {
                "stage":   "audio_processing",
                "message": "librosa could not decode ...",
            },
        }

    Notes
    -----
    * Temporary files are cleaned up automatically after each run unless
      ``config.SAVE_INTERMEDIATE_FILES`` is ``True`` (development mode).
    * Timing is wall-clock time; each stage is timed individually and
      included in ``INFO`` logs for performance profiling.
    """
    pipeline_start = time.time()
    steps: list[str] = []

    # Track paths we may need to clean up
    saved_path      = None
    processed_path  = None
    vocals_path     = None

    logger.info("══════════════════════════════════════════")
    logger.info("  Pipeline started")
    logger.info("══════════════════════════════════════════")

    # ─────────────────────────────────────────────────────────────────────────
    # STAGE 1 — Save uploaded file
    # ─────────────────────────────────────────────────────────────────────────
    logger.info("[ 1 / 5 ]  Saving uploaded file …")
    stage_start = time.time()

    try:
        saved_path = save_file(uploaded_file)
        steps.append("file_saved")
        logger.info("File saved → %s  (%.2fs)", saved_path, time.time() - stage_start)
    except (ValueError, OSError, FileNotFoundError) as exc:
        return _failure(exc, steps, time.time() - pipeline_start, "file_save")

    # ─────────────────────────────────────────────────────────────────────────
    # STAGE 2 — Audio processing
    # ─────────────────────────────────────────────────────────────────────────
    logger.info("[ 2 / 5 ]  Processing audio …")
    stage_start = time.time()

    try:
        processed_path = process_audio(saved_path)
        steps.append("audio_processed")
        logger.info("Audio processed → %s  (%.2fs)", processed_path, time.time() - stage_start)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        _maybe_cleanup(vocals_path, processed_path)
        return _failure(exc, steps, time.time() - pipeline_start, "audio_processing")

    # ─────────────────────────────────────────────────────────────────────────
    # STAGE 3 — Vocal separation
    # ─────────────────────────────────────────────────────────────────────────
    logger.info("[ 3 / 5 ]  Separating vocals …")
    stage_start = time.time()

    try:
        vocals_path = separate_vocals(processed_path)
        steps.append("vocals_separated")
        logger.info("Vocals extracted → %s  (%.2fs)", vocals_path, time.time() - stage_start)
    except (FileNotFoundError, RuntimeError) as exc:
        _maybe_cleanup(vocals_path, processed_path)
        return _failure(exc, steps, time.time() - pipeline_start, "vocal_separation")

    # ─────────────────────────────────────────────────────────────────────────
    # STAGE 4 — Transcription
    # ─────────────────────────────────────────────────────────────────────────
    logger.info("[ 4 / 5 ]  Transcribing audio …")
    stage_start = time.time()

    try:
        transcription = transcribe_audio(vocals_path)
        steps.append("audio_transcribed")
        logger.info(
            "Transcription complete — language: %s, words: %d  (%.2fs)",
            transcription.get("language", "?"),
            transcription.get("word_count", 0),
            time.time() - stage_start,
        )
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        _maybe_cleanup(vocals_path, processed_path)
        return _failure(exc, steps, time.time() - pipeline_start, "transcription")

    # ─────────────────────────────────────────────────────────────────────────
    # STAGE 5 — Text cleaning & lyrics formatting
    # ─────────────────────────────────────────────────────────────────────────
    logger.info("[ 5 / 5 ]  Cleaning and formatting lyrics …")
    stage_start = time.time()

    try:
        cleaned = process_text(transcription)
        steps.append("text_cleaned")
        logger.info(
            "Lyrics ready — %d lines  (%.2fs)",
            len(cleaned.get("lyrics", "").splitlines()),
            time.time() - stage_start,
        )
    except (TypeError, KeyError, Exception) as exc:
        return _failure(exc, steps, time.time() - pipeline_start, "text_cleaning")

    # ─────────────────────────────────────────────────────────────────────────
    # CLEANUP — remove intermediate temp files (respects config flag)
    # ─────────────────────────────────────────────────────────────────────────
    _maybe_cleanup(vocals_path, processed_path)

    # ─────────────────────────────────────────────────────────────────────────
    # SUCCESS — assemble and return final payload
    # ─────────────────────────────────────────────────────────────────────────
    total_elapsed = time.time() - pipeline_start

    data: dict[str, Any] = {
        **cleaned,                          # lyrics, cleaned_text, original_text,
                                            # segments, language, word_count,
                                            # segment_count, model_size
        "source_file": saved_path,
    }

    logger.info("══════════════════════════════════════════")
    logger.info("  Pipeline complete in %.2fs", total_elapsed)
    logger.info("══════════════════════════════════════════")

    return _success(data, steps, total_elapsed)


# =============================================================================
# 5. INTERNAL CLEANUP HELPER
# =============================================================================

def _maybe_cleanup(*paths) -> None:
    """
    Delete specific intermediate files unless the config says to keep them.

    Silently ignores ``None`` entries so callers don't have to guard for
    stages that didn't produce a file.
    """
    if config.SAVE_INTERMEDIATE_FILES and config.DEBUG:
        logger.debug("Skipping cleanup (SAVE_INTERMEDIATE_FILES=True).")
        return

    for path in paths:
        if path is not None:
            cleanup_temp_files(path)


# =============================================================================
# QUICK SANITY-CHECK  (python app/upload.py)
# =============================================================================
if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s │ %(name)s │ %(message)s",
        datefmt="%H:%M:%S",
    )

    # ── Edge case: no file ────────────────────────────────────────────────────
    print("=== Edge case: None input ===")
    result = process_upload(None)
    print(f"  success : {result['success']}")
    print(f"  stage   : {result['error']['stage'] if result['error'] else '—'}")
    print(f"  message : {result['error']['message'] if result['error'] else '—'}")

    # ── Edge case: non-existent path ──────────────────────────────────────────
    print("\n=== Edge case: missing file path ===")
    result = process_upload("ghost_track.mp3")
    print(f"  success : {result['success']}")
    print(f"  stage   : {result['error']['stage'] if result['error'] else '—'}")
    print(f"  message : {result['error']['message'] if result['error'] else '—'}")

    # ── Full pipeline on a real file ──────────────────────────────────────────
    if len(sys.argv) > 1:
        print(f"\n=== Full pipeline: {sys.argv[1]} ===")
        result = process_upload(sys.argv[1])

        if result["success"]:
            d = result["data"]
            print(f"\n  ✅ Success in {result['processing_time']}s")
            print(f"  Language      : {d['language']}")
            print(f"  Words         : {d['word_count']}")
            print(f"  Segments      : {d['segment_count']}")
            print(f"  Steps done    : {result['steps_completed']}")
            print(f"\n  Lyrics:\n")
            for line in d["lyrics"].splitlines():
                print(f"    {line}")
        else:
            print(f"\n  ❌ Failed at stage '{result['error']['stage']}'")
            print(f"     {result['error']['message']}")
    else:
        print("\nTip: pass an audio file to run the full pipeline:")
        print("     python app/upload.py data/input/song.mp3")
        print("\n✅  upload.py self-check complete.")