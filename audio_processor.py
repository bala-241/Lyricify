# =============================================================================
# app/audio_processor.py — Audio Preparation Pipeline
# =============================================================================
# Responsibilities:
#   • Convert any input format → WAV
#   • Resample to 16 000 Hz  (Whisper requirement)
#   • Downmix stereo → mono  (Whisper requirement)
#   • Normalize amplitude    (improves transcription accuracy)
#   • Orchestrate the full pipeline via process_audio()
#
# Connects to:
#   file_handler.py      → provides validated input paths
#   vocal_separator.py   → receives the processed WAV path
#
# Libraries:
#   pydub      → format conversion  (AudioSegment)
#   librosa    → loading / resampling / mono conversion
#   soundfile  → writing processed WAV files
#   numpy      → amplitude normalization
# =============================================================================

# 1. IMPORTS
# =============================================================================
import logging
from pathlib import Path
from typing import Optional

import librosa
import numpy as np
import soundfile as sf
from pydub import AudioSegment

from app import config
from app.utils.file_handler import ensure_directory

# =============================================================================
# 2. MODULE LOGGER
# =============================================================================

logger = logging.getLogger(__name__)

# =============================================================================
# 3. INTERNAL HELPERS
# =============================================================================

def _temp_path(stem: str, suffix: str) -> Path:
    """
    Build a path inside TEMP_DIR using *stem* + *suffix*.

    Example
    -------
    _temp_path("song", "_resampled") → Path("<TEMP_DIR>/song_resampled.wav")
    """
    ensure_directory(config.TEMP_DIR)
    return Path(config.TEMP_DIR) / f"{stem}{suffix}.wav"


def _load_audio(
    input_path: str,
    sr: Optional[int] = None,
    mono: bool = False,
) -> tuple[np.ndarray, int]:
    """
    Load an audio file with librosa and return ``(samples, sample_rate)``.

    Parameters
    ----------
    input_path : str
        Path to the audio file.
    sr : int | None
        Target sample rate for resampling.  ``None`` → keep native rate.
    mono : bool
        If ``True``, downmix to a single channel.

    Raises
    ------
    FileNotFoundError
        If *input_path* does not point to an existing file.
    ValueError
        If the loaded audio array is empty.
    RuntimeError
        If librosa cannot decode the file.
    """
    path = Path(input_path)
    if not path.exists():
        raise FileNotFoundError(f"Audio file not found: {path}")

    logger.debug("Loading audio from '%s' (sr=%s, mono=%s).", path, sr, mono)

    try:
        audio, sample_rate = librosa.load(str(path), sr=sr, mono=mono)
    except Exception as exc:
        raise RuntimeError(
            f"librosa could not decode '{path}'. "
            f"Ensure the file is a valid audio file. Original error: {exc}"
        ) from exc

    if audio is None or len(audio) == 0:
        raise ValueError(f"Loaded audio is empty (0 samples): '{path}'")

    # Warn if the track appears to be silent (all near-zero samples)
    peak = np.max(np.abs(audio))
    if peak < 1e-6:
        logger.warning(
            "Audio '%s' appears to be silent (peak amplitude = %.2e).", path, peak
        )

    return audio, sample_rate


# =============================================================================
# 4. STEP 1 — FORMAT CONVERSION
# =============================================================================

def convert_to_wav(input_path: str) -> str:
    """
    Convert an audio file of any supported format to an uncompressed WAV.

    Uses ``pydub.AudioSegment`` so it handles mp3, flac, ogg, m4a, etc.
    The result is written to ``config.TEMP_DIR`` and the original is never
    modified.

    Parameters
    ----------
    input_path : str
        Path to the source audio file.

    Returns
    -------
    str
        Absolute path to the converted WAV file inside TEMP_DIR.

    Raises
    ------
    FileNotFoundError
        If *input_path* does not exist.
    ValueError
        If the file extension is not in ``config.SUPPORTED_FORMATS``.
    RuntimeError
        If pydub fails to decode the file.
    """
    path = Path(input_path)

    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    ext = path.suffix.lstrip(".").lower()
    if ext not in config.SUPPORTED_FORMATS:
        raise ValueError(
            f"Unsupported format '.{ext}'. "
            f"Supported: {config.SUPPORTED_FORMATS}"
        )

    # If the source is already a WAV we still copy it into TEMP_DIR so the
    # rest of the pipeline always works on temp files only.
    out_path = _temp_path(path.stem, "")          # e.g. song.wav

    logger.info("Step 1/4 — Converting '%s' → WAV …", path.name)

    try:
        segment = AudioSegment.from_file(str(path), format=ext)
        segment.export(str(out_path), format="wav")
    except Exception as exc:
        raise RuntimeError(
            f"pydub failed to convert '{path}'. "
            f"Check that ffmpeg is installed. Original error: {exc}"
        ) from exc

    logger.info("Converted to WAV → %s", out_path)
    return str(out_path)


# =============================================================================
# 5. STEP 2 — RESAMPLING
# =============================================================================

def resample_audio(input_path: str) -> str:
    """
    Resample the audio to ``config.TARGET_SAMPLE_RATE`` (default 16 000 Hz).

    Whisper was trained on 16 kHz audio; mismatched sample rates degrade
    transcription quality.

    Parameters
    ----------
    input_path : str
        Path to a WAV (or other librosa-readable) file.

    Returns
    -------
    str
        Absolute path to the resampled WAV in TEMP_DIR, named
        ``<stem>_resampled.wav``.
    """
    path     = Path(input_path)
    out_path = _temp_path(path.stem.removesuffix("_mono")
                                   .removesuffix("_normalized"), "_resampled")

    logger.info(
        "Step 2/4 — Resampling to %d Hz …", config.TARGET_SAMPLE_RATE
    )

    audio, native_sr = _load_audio(input_path, sr=None, mono=False)

    if native_sr == config.TARGET_SAMPLE_RATE:
        logger.info(
            "Sample rate already %d Hz — skipping resample, copying file.",
            native_sr,
        )
        sf.write(str(out_path), audio.T if audio.ndim == 2 else audio,
                 native_sr, subtype="PCM_16")
        return str(out_path)

    logger.debug(
        "Native sample rate %d Hz → target %d Hz.", native_sr, config.TARGET_SAMPLE_RATE
    )

    # librosa.load with sr= does resampling for us; reload with target sr
    audio_resampled, _ = _load_audio(
        input_path, sr=config.TARGET_SAMPLE_RATE, mono=False
    )

    # soundfile expects shape (samples,) for mono or (samples, channels) for multi
    write_data = audio_resampled.T if audio_resampled.ndim == 2 else audio_resampled
    sf.write(str(out_path), write_data, config.TARGET_SAMPLE_RATE, subtype="PCM_16")

    logger.info("Resampled to %d Hz → %s", config.TARGET_SAMPLE_RATE, out_path)
    return str(out_path)


# =============================================================================
# 6. STEP 3 — MONO CONVERSION
# =============================================================================

def convert_to_mono(input_path: str) -> str:
    """
    Downmix a stereo (or multi-channel) audio file to a single mono channel.

    When ``config.AUDIO_CHANNELS`` is already 1 the step is effectively a
    no-op (librosa returns mono when ``mono=True``).

    Parameters
    ----------
    input_path : str
        Path to the audio file (typically the resampled WAV).

    Returns
    -------
    str
        Absolute path to the mono WAV in TEMP_DIR, named
        ``<stem_base>_mono.wav``.
    """
    path = Path(input_path)
    # Strip known suffixes so the base stem stays clean
    base  = path.stem
    for suffix in ("_resampled", "_normalized"):
        base = base.removesuffix(suffix)
    out_path = _temp_path(base, "_mono")

    logger.info("Step 3/4 — Converting to mono …")

    # librosa.load with mono=True averages channels automatically
    audio, sr = _load_audio(input_path, sr=None, mono=True)

    if audio.ndim != 1:
        raise RuntimeError(
            f"Expected 1-D array after mono conversion, got shape {audio.shape}."
        )

    sf.write(str(out_path), audio, sr, subtype="PCM_16")
    logger.info("Converted to mono → %s", out_path)
    return str(out_path)


# =============================================================================
# 7. STEP 4 — AMPLITUDE NORMALIZATION
# =============================================================================

def normalize_audio(input_path: str) -> str:
    """
    Normalize audio amplitude so the peak value is ±1.0 (full-scale).

    Peak normalization ensures that very quiet or very loud recordings are
    brought to a consistent level before being fed to Whisper.

    Parameters
    ----------
    input_path : str
        Path to the audio file (typically the mono WAV).

    Returns
    -------
    str
        Absolute path to the normalized WAV in TEMP_DIR, named
        ``<stem_base>_normalized.wav``.

    Notes
    -----
    If the audio is entirely silent (peak < 1e-9) the array is left unchanged
    and a warning is logged to prevent division-by-zero.
    """
    path = Path(input_path)
    base = path.stem
    for suffix in ("_resampled", "_mono"):
        base = base.removesuffix(suffix)
    out_path = _temp_path(base, "_normalized")

    logger.info("Step 4/4 — Normalizing volume …")

    audio, sr = _load_audio(input_path, sr=None, mono=False)

    peak = np.max(np.abs(audio))

    if peak < 1e-9:
        logger.warning(
            "Audio is silent (peak = %.2e); skipping normalization.", peak
        )
    else:
        audio = audio / peak                        # scale to [-1.0, 1.0]
        logger.debug("Normalized peak %.4f → 1.0", peak)

    write_data = audio.T if audio.ndim == 2 else audio
    sf.write(str(out_path), write_data, sr, subtype="PCM_16")

    logger.info("Normalized audio → %s", out_path)
    return str(out_path)


# =============================================================================
# 8. MAIN PIPELINE — process_audio()
# =============================================================================

def process_audio(input_path: str) -> str:
    """
    Run the complete audio-preparation pipeline on *input_path*.

    Pipeline
    --------
    convert_to_wav()  →  resample_audio()  →  convert_to_mono()
                      →  normalize_audio() →  return final path

    Parameters
    ----------
    input_path : str
        Path to any supported audio file (mp3, wav, flac).

    Returns
    -------
    str
        Absolute path to the fully processed, Whisper-ready WAV file.

    Raises
    ------
    FileNotFoundError
        If *input_path* does not exist.
    ValueError
        If the format is unsupported or the audio is empty.
    RuntimeError
        If any processing step fails unexpectedly.

    Example
    -------
    >>> ready_path = process_audio("data/input/song_20260329_a1b2.mp3")
    >>> # ready_path → "data/temp/song_normalized.wav"
    """
    logger.info("━━━  Audio processing pipeline started  ━━━")
    logger.info("Input: %s", input_path)

    try:
        wav_path        = convert_to_wav(input_path)
        resampled_path  = resample_audio(wav_path)
        mono_path       = convert_to_mono(resampled_path)
        final_path      = normalize_audio(mono_path)
    except (FileNotFoundError, ValueError, RuntimeError):
        # Re-raise known errors with their original messages intact
        raise
    except Exception as exc:
        # Wrap unexpected errors so callers get a consistent exception type
        raise RuntimeError(
            f"Unexpected error in audio processing pipeline: {exc}"
        ) from exc

    logger.info("━━━  Pipeline complete  →  %s  ━━━", final_path)
    return final_path


# =============================================================================
# QUICK SANITY-CHECK  (python app/audio_processor.py)
# =============================================================================
if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(levelname)-8s │ %(name)s │ %(message)s",
    )

    if len(sys.argv) < 2:
        print("Usage: python audio_processor.py <path/to/audio_file>")
        print("Running internal helper tests instead …\n")

        # ── _temp_path ─────────────────────────────────────────────────────
        p = _temp_path("demo_song", "_resampled")
        print(f"_temp_path test         → {p}")

        # ── missing file guard ─────────────────────────────────────────────
        try:
            convert_to_wav("nonexistent.mp3")
        except FileNotFoundError as e:
            print(f"FileNotFoundError (OK) → {e}")

        # ── unsupported format guard ───────────────────────────────────────
        fake = Path(config.TEMP_DIR) / "test.xyz"
        fake.write_bytes(b"\x00")
        try:
            convert_to_wav(str(fake))
        except ValueError as e:
            print(f"ValueError (OK)        → {e}")
        finally:
            fake.unlink(missing_ok=True)

        print("\n✅  audio_processor self-check complete (no real audio used).")
    else:
        # Full pipeline on a real file
        result = process_audio(sys.argv[1])
        print(f"\n✅  Processed file ready: {result}")