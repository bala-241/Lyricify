# =============================================================================
# app/file_handler.py — Gatekeeper of the System
# =============================================================================
# Responsibilities:
#   • Validate incoming files (extension + size)
#   • Generate unique, safe filenames
#   • Save uploads to INPUT_DIR
#   • Clean up TEMP_DIR after processing
#   • Provide small, reusable path utilities
#
# Connects to:
#   upload.py          → save_file() / validate_file()
#   audio_processor.py → paths returned by save_file()
#   pipeline cleanup   → cleanup_temp_files()
# =============================================================================

# 1. IMPORTS
# =============================================================================
import logging
import os
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Union

from app import config

# =============================================================================
# 2. MODULE LOGGER
# =============================================================================

logger = logging.getLogger(__name__)

# =============================================================================
# 3. UTILITIES
# =============================================================================

def get_file_extension(filename: str) -> str:
    """
    Return the lowercase extension of *filename* WITHOUT the leading dot.

    Examples
    --------
    >>> get_file_extension("song.MP3")
    'mp3'
    >>> get_file_extension("track")
    ''
    """
    return Path(filename).suffix.lstrip(".").lower()


def ensure_directory(path: Union[str, Path]) -> Path:
    """
    Guarantee that *path* exists as a directory.

    Creates intermediate parents if needed.  Safe to call on already-existing
    directories.  Returns the resolved ``Path`` object so callers can chain.

    Note: config.py already bootstraps the main dirs at import time; this
    helper makes file_handler independently reliable (e.g. in tests or CLIs
    that skip the normal app entry-point).
    """
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    logger.debug("Directory ensured: %s", path)
    return path


# =============================================================================
# 4. FILENAME GENERATION
# =============================================================================

def generate_filename(original_name: str) -> str:
    """
    Build a unique, filesystem-safe filename from *original_name*.

    Strategy
    --------
    1. Strip the extension.
    2. Replace every non-alphanumeric character with ``_``.
    3. Collapse consecutive underscores → single ``_``.
    4. Strip leading/trailing underscores.
    5. Append a timestamp (``YYYYMMDD_HHMMSS``) for human readability.
    6. Append a short UUID fragment to guarantee uniqueness even if two
       files are processed within the same second.
    7. Re-attach the original extension (lowercased).

    Parameters
    ----------
    original_name : str
        The filename as received from the user / upload widget.

    Returns
    -------
    str
        A safe, unique filename, e.g. ``song_20260329_183012_a3f1.mp3``.

    Raises
    ------
    ValueError
        If *original_name* is empty or has no usable stem after sanitisation.

    Examples
    --------
    >>> generate_filename("My Song (feat. Artist).mp3")
    'My_Song_feat_Artist_20260329_183012_a3f1.mp3'
    """
    if not original_name or not original_name.strip():
        raise ValueError("original_name must be a non-empty string.")

    original_path = Path(original_name)
    stem          = original_path.stem          # name without extension
    ext           = original_path.suffix.lower()  # e.g. ".mp3"

    # --- sanitise stem ---
    safe_stem = re.sub(r"[^\w]", "_", stem)       # keep word chars, replace rest
    safe_stem = re.sub(r"_+", "_", safe_stem)      # collapse runs of underscores
    safe_stem = safe_stem.strip("_")               # remove leading / trailing _

    if not safe_stem:
        raise ValueError(
            f"Filename '{original_name}' yields an empty stem after sanitisation."
        )

    timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
    uid_frag   = uuid.uuid4().hex[:4]             # 4-char uniqueness suffix

    new_name = f"{safe_stem}_{timestamp}_{uid_frag}{ext}"
    logger.debug("Generated filename: '%s' → '%s'", original_name, new_name)
    return new_name


# =============================================================================
# 5. VALIDATION
# =============================================================================

def validate_file(file) -> tuple[bool, str]:
    """
    Check *file* against extension and size rules defined in ``config``.

    Accepts both Streamlit ``UploadedFile`` objects and plain ``Path`` /
    ``str`` paths so the function works from the web UI and the CLI alike.

    Parameters
    ----------
    file : UploadedFile | str | Path
        The file to validate.

    Returns
    -------
    (is_valid : bool, reason : str)
        ``reason`` is an empty string when ``is_valid`` is ``True``.

    Examples
    --------
    >>> ok, msg = validate_file(Path("audio/track.mp3"))
    >>> if not ok:
    ...     print(msg)
    """
    # ── resolve name & size depending on type ────────────────────────────────
    if hasattr(file, "name") and hasattr(file, "size"):
        # Streamlit UploadedFile
        filename  = file.name
        size_mb   = file.size / (1024 * 1024)
    elif isinstance(file, (str, Path)):
        filepath  = Path(file)
        if not filepath.exists():
            reason = f"File not found: {filepath}"
            logger.warning(reason)
            return False, reason
        filename = filepath.name
        size_mb  = filepath.stat().st_size / (1024 * 1024)
    else:
        reason = f"Unsupported file type passed to validate_file(): {type(file)}"
        logger.error(reason)
        return False, reason

    # ── extension check ───────────────────────────────────────────────────────
    if not config.is_allowed_file(filename):
        ext    = get_file_extension(filename)
        reason = (
            f"Extension '.{ext}' is not allowed. "
            f"Accepted: {config.ALLOWED_EXTENSIONS}"
        )
        logger.warning("Validation failed — %s", reason)
        return False, reason

    # ── size check ────────────────────────────────────────────────────────────
    if size_mb > config.MAX_FILE_SIZE_MB:
        reason = (
            f"File size {size_mb:.2f} MB exceeds the "
            f"{config.MAX_FILE_SIZE_MB} MB limit."
        )
        logger.warning("Validation failed — %s", reason)
        return False, reason

    logger.debug("File '%s' passed validation (%.2f MB).", filename, size_mb)
    return True, ""


# =============================================================================
# 6. SAVING FILES
# =============================================================================

def save_file(uploaded_file) -> str:
    """
    Validate, rename, and persist *uploaded_file* to ``config.INPUT_DIR``.

    Compatible with:
    * **Streamlit** ``UploadedFile`` — has ``.name``, ``.size``, ``.read()``.
    * **CLI / Path** — a ``str`` or ``pathlib.Path`` to an existing file
      (the file is *copied* into INPUT_DIR under a new safe name).

    Parameters
    ----------
    uploaded_file : UploadedFile | str | Path
        The file object or path to save.

    Returns
    -------
    str
        Absolute path of the saved file inside INPUT_DIR.

    Raises
    ------
    ValueError
        If validation fails (wrong extension, oversized, missing file, etc.).
    OSError
        If the file cannot be written to disk.

    Flow
    ----
    validate_file() → generate_filename() → write to INPUT_DIR → return path
    """
    # ── guard: ensure destination directory exists ────────────────────────────
    ensure_directory(config.INPUT_DIR)

    # ── validate BEFORE touching the filesystem ───────────────────────────────
    is_valid, reason = validate_file(uploaded_file)
    if not is_valid:
        logger.error("save_file() rejected: %s", reason)
        raise ValueError(f"File validation failed: {reason}")

    # ── resolve original filename ─────────────────────────────────────────────
    if hasattr(uploaded_file, "name"):
        original_name = uploaded_file.name          # Streamlit path
    else:
        original_name = Path(uploaded_file).name    # CLI path

    # ── generate safe unique name ─────────────────────────────────────────────
    safe_name    = generate_filename(original_name)
    destination  = config.INPUT_DIR / safe_name

    # Extremely unlikely, but be safe: keep appending new UUID frags if needed
    while destination.exists():
        safe_name   = generate_filename(original_name)
        destination = config.INPUT_DIR / safe_name
        logger.debug("Collision detected — retrying with: %s", safe_name)

    # ── write bytes to disk ───────────────────────────────────────────────────
    try:
        if hasattr(uploaded_file, "read"):
            # Streamlit UploadedFile  (or any file-like object)
            raw_bytes = uploaded_file.read()
            if not raw_bytes:
                raise ValueError("Uploaded file is empty (0 bytes).")
            destination.write_bytes(raw_bytes)
        else:
            # CLI path — copy the source file
            shutil.copy2(str(uploaded_file), str(destination))

        logger.info("File saved → %s", destination)
        return str(destination)

    except OSError as exc:
        logger.exception("Failed to save file to '%s': %s", destination, exc)
        raise


# =============================================================================
# 7. CLEANUP
# =============================================================================

def cleanup_temp_files(file_path: Union[str, Path, None] = None) -> None:
    """
    Remove temporary files produced during audio processing.

    Parameters
    ----------
    file_path : str | Path | None
        * **Provided** → delete only that specific file (or directory).
        * **None**     → wipe the entire ``config.TEMP_DIR``, then re-create
          the empty folder so downstream code doesn't trip on a missing dir.

    Behaviour
    ---------
    * Missing paths are logged as warnings, not raised as exceptions — cleanup
      should never crash the main pipeline.
    * When ``config.SAVE_INTERMEDIATE_FILES`` is ``True`` (development mode),
      the function logs a notice and returns early so you can inspect outputs.
    """
    if config.SAVE_INTERMEDIATE_FILES and config.DEBUG:
        logger.info(
            "cleanup_temp_files() skipped — "
            "SAVE_INTERMEDIATE_FILES=True (development mode)."
        )
        return

    if file_path is not None:
        # ── delete a single file or sub-directory ─────────────────────────────
        target = Path(file_path)
        if not target.exists():
            logger.warning(
                "cleanup_temp_files(): path does not exist, skipping — %s",
                target,
            )
            return

        try:
            if target.is_dir():
                shutil.rmtree(target)
                logger.info("Removed temp directory: %s", target)
            else:
                target.unlink()
                logger.info("Removed temp file: %s", target)
        except OSError as exc:
            logger.error("Could not remove '%s': %s", target, exc)

    else:
        # ── wipe entire TEMP_DIR ──────────────────────────────────────────────
        temp_dir = Path(config.TEMP_DIR)
        if not temp_dir.exists():
            logger.warning("TEMP_DIR does not exist, nothing to clean.")
            return

        removed = 0
        errors  = 0
        for item in temp_dir.iterdir():
            try:
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
                removed += 1
                logger.debug("Removed: %s", item)
            except OSError as exc:
                errors += 1
                logger.error("Could not remove '%s': %s", item, exc)

        # Re-create the empty folder so it's ready for the next run
        ensure_directory(temp_dir)
        logger.info(
            "TEMP_DIR cleaned — %d item(s) removed, %d error(s).", removed, errors
        )


# =============================================================================
# QUICK SANITY-CHECK  (python app/file_handler.py)
# =============================================================================
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    # ── generate_filename ─────────────────────────────────────────────────────
    samples = ["song.mp3", "My Song (feat. Artist).WAV", "track", "!!.mp3"]
    print("\n=== generate_filename() ===")
    for s in samples:
        try:
            print(f"  {s!r:40s} → {generate_filename(s)}")
        except ValueError as e:
            print(f"  {s!r:40s} → ERROR: {e}")

    # ── get_file_extension ────────────────────────────────────────────────────
    print("\n=== get_file_extension() ===")
    for s in ["track.MP3", "file.wav", "noext"]:
        print(f"  {s!r:20s} → '{get_file_extension(s)}'")

    # ── validate_file (path-based) ────────────────────────────────────────────
    print("\n=== validate_file() — path mode ===")
    dummy = Path(config.INPUT_DIR) / "test_song.mp3"
    dummy.write_bytes(b"\x00" * 100)          # tiny fake file
    ok, msg = validate_file(dummy)
    print(f"  test_song.mp3 → valid={ok}, msg={msg!r}")
    dummy.unlink()

    # ── ensure_directory ──────────────────────────────────────────────────────
    print("\n=== ensure_directory() ===")
    test_dir = Path(config.TEMP_DIR) / "subdir_test"
    ensure_directory(test_dir)
    print(f"  Created: {test_dir.exists()} → {test_dir}")
    test_dir.rmdir()

    print("\n✅  file_handler self-check complete.")