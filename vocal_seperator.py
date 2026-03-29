# =============================================================================
# app/vocal_separator.py — AI Vocal Extraction
# =============================================================================
# Responsibilities:
#   • Load the Spleeter model once and cache it for the process lifetime
#   • Separate vocals from an audio file using Spleeter's Python API
#   • Return the path to vocals.wav for downstream transcription
#
# Pipeline position:
#   audio_processor.py  →  vocal_separator.py  →  transcriber.py
#
# Library:
#   spleeter  → Separator (wraps a TensorFlow source-separation model)
# =============================================================================

# 1. IMPORTS
# =============================================================================
import logging
from pathlib import Path

from app import config
from app.utils.file_handler import ensure_directory

# =============================================================================
# 2. MODULE LOGGER
# =============================================================================

logger = logging.getLogger(__name__)

# =============================================================================
# 3. GLOBAL MODEL CACHE
# =============================================================================

# Spleeter model is large; loading it takes several seconds.
# We store the instance here so load_separator() is a true no-op on every
# call after the first one.
_separator_instance = None


# =============================================================================
# 4. MODEL LOADER
# =============================================================================

def load_separator():
    """
    Return a cached ``spleeter.separator.Separator`` instance.

    The model is initialised on the **first call only**.  Every subsequent
    call returns the already-loaded instance immediately (O(1)).

    Model used is ``config.SPLEETER_MODEL`` (default ``"spleeter:2stems"``),
    which produces two stems:

    * ``vocals.wav``        ← what we need
    * ``accompaniment.wav`` ← discarded

    Returns
    -------
    spleeter.separator.Separator
        Ready-to-use separator instance.

    Raises
    ------
    RuntimeError
        If Spleeter cannot be imported or the model fails to initialise.
    """
    global _separator_instance

    if _separator_instance is not None:
        logger.debug("Spleeter model already loaded — reusing cached instance.")
        return _separator_instance

    logger.info("Loading Spleeter model '%s' …", config.SPLEETER_MODEL)

    try:
        # Import here so the module can be imported even if spleeter is not
        # installed yet (unit tests can mock at this level).
        from spleeter.separator import Separator

        _separator_instance = Separator(config.SPLEETER_MODEL)
        logger.info("Spleeter model loaded successfully.")
        return _separator_instance

    except ImportError as exc:
        raise RuntimeError(
            "Spleeter is not installed. "
            "Run: pip install spleeter"
        ) from exc

    except Exception as exc:
        raise RuntimeError(
            f"Failed to initialise Spleeter model '{config.SPLEETER_MODEL}': {exc}"
        ) from exc


# =============================================================================
# 5. VOCAL SEPARATION
# =============================================================================

def separate_vocals(input_path: str) -> str:
    """
    Extract the vocal stem from *input_path* using Spleeter.

    Spleeter writes its output under a sub-directory named after the input
    file stem::

        TEMP_DIR/
            <stem>/
                vocals.wav          ← returned
                accompaniment.wav   ← ignored

    The model is loaded once via :func:`load_separator` and reused on every
    subsequent call.

    Parameters
    ----------
    input_path : str
        Path to a processed WAV file (output of ``audio_processor.process_audio``).

    Returns
    -------
    str
        Absolute path to ``vocals.wav`` inside TEMP_DIR.

    Raises
    ------
    FileNotFoundError
        If *input_path* does not exist on disk.
    RuntimeError
        If Spleeter fails during separation, or if ``vocals.wav`` is not
        produced in the expected output location.

    Flow
    ----
    validate input  →  load_separator()  →  separate_to_file()
                    →  locate vocals.wav  →  return path
    """
    # ── 1. Validate input ─────────────────────────────────────────────────────
    path = Path(input_path)

    if not path.exists():
        raise FileNotFoundError(
            f"Input audio file not found: '{path}'. "
            "Ensure audio_processor.process_audio() has run first."
        )

    stem = path.stem          # e.g. "song_normalized"  (used by Spleeter for output dir)
    logger.info("━━━  Vocal separation started  ━━━")
    logger.info("Input : %s", path)

    # ── 2. Prepare output directory ───────────────────────────────────────────
    output_dir = Path(config.TEMP_DIR)
    ensure_directory(output_dir)

    # ── 3. Load (or reuse) model ──────────────────────────────────────────────
    separator = load_separator()

    # ── 4. Run separation ─────────────────────────────────────────────────────
    logger.info("Separating vocals (this may take a moment) …")

    try:
        # separate_to_file writes:
        #   <output_dir>/<stem>/vocals.wav
        #   <output_dir>/<stem>/accompaniment.wav
        separator.separate_to_file(
            audio_descriptor=str(path),
            destination=str(output_dir),
            codec="wav",
            synchronous=True,           # block until separation is complete
        )
    except Exception as exc:
        raise RuntimeError(
            f"Spleeter separation failed for '{path}': {exc}"
        ) from exc

    # ── 5. Locate vocals.wav ──────────────────────────────────────────────────
    # Spleeter names the sub-folder after the input file stem
    vocals_path = output_dir / stem / "vocals.wav"

    if not vocals_path.exists():
        # Collect what WAS written (useful for debugging)
        stem_dir = output_dir / stem
        written  = (
            [f.name for f in stem_dir.iterdir()]
            if stem_dir.exists()
            else "directory not created"
        )
        raise RuntimeError(
            f"vocals.wav was not produced by Spleeter.\n"
            f"Expected: '{vocals_path}'\n"
            f"Found in output dir: {written}"
        )

    logger.info("Vocals extracted → %s", vocals_path)
    logger.info("━━━  Vocal separation complete  ━━━")

    return str(vocals_path)


# =============================================================================
# 6. ACCESSOR FOR TESTS / RESET
# =============================================================================

def reset_separator() -> None:
    """
    Clear the cached Spleeter instance.

    Intended for testing only — forces :func:`load_separator` to re-initialise
    the model on the next call.
    """
    global _separator_instance
    _separator_instance = None
    logger.debug("Spleeter model cache cleared.")


# =============================================================================
# QUICK SANITY-CHECK  (python app/vocal_separator.py)
# =============================================================================
if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(levelname)-8s │ %(name)s │ %(message)s",
    )

    # ── Guard: missing file ───────────────────────────────────────────────────
    print("=== Edge case: missing input file ===")
    try:
        separate_vocals("nonexistent.wav")
    except FileNotFoundError as e:
        print(f"FileNotFoundError (OK) → {e}\n")

    # ── Run on a real file if provided ────────────────────────────────────────
    if len(sys.argv) > 1:
        audio_path = sys.argv[1]
        print(f"=== Running separation on: {audio_path} ===")
        result = separate_vocals(audio_path)
        print(f"\n✅  Vocals extracted → {result}")
    else:
        print("Tip: pass a processed WAV path to test the full pipeline:")
        print("     python vocal_separator.py data/temp/song_normalized.wav")
        print("\n✅  vocal_separator self-check complete (no real audio used).")