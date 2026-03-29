#!/usr/bin/env python3
# =============================================================================
# run.py — Application Entry Point
# =============================================================================
# Usage:
#   python run.py              → start with default settings
#   python run.py --debug      → force DEBUG log level
#   python run.py --port 8502  → run on a custom port
#
# What this file does:
#   1. Validates the environment (Python version, required directories)
#   2. Initialises the central logging system
#   3. Pre-flight checks config values
#   4. Launches the Streamlit UI via subprocess (same Python env, no PATH issues)
# =============================================================================

# 1. IMPORTS
# =============================================================================
import argparse
import os
import subprocess
import sys
from pathlib import Path

# =============================================================================
# 2. PYTHON VERSION GUARD  (must come before any app imports)
# =============================================================================

_REQUIRED = (3, 9)

if sys.version_info < _REQUIRED:
    print(
        f"❌  Python {_REQUIRED[0]}.{_REQUIRED[1]}+ is required. "
        f"You are running {sys.version.split()[0]}."
    )
    sys.exit(1)

# =============================================================================
# 3. ENTRY-POINT FUNCTION
# =============================================================================

def main() -> None:
    """
    Bootstrap the application and launch the Streamlit UI.

    Steps
    -----
    1. Parse CLI arguments (optional port / debug flag).
    2. Initialise the central logger so every subsequent log call is formatted.
    3. Run environment pre-flight checks.
    4. Launch ``app/main.py`` via ``streamlit run``.
    """

    # ── CLI arguments ─────────────────────────────────────────────────────────
    parser = argparse.ArgumentParser(
        description="AI Song Lyrics Generator — entry point"
    )
    parser.add_argument(
        "--port", type=int, default=8501,
        help="Port for the Streamlit server (default: 8501)"
    )
    parser.add_argument(
        "--debug", action="store_true",
        help="Override LOG_LEVEL to DEBUG for this session"
    )
    args = parser.parse_args()

    # ── Optional: override log level before logger is initialised ─────────────
    if args.debug:
        os.environ["LOG_LEVEL_OVERRIDE"] = "DEBUG"

    # ── Initialise central logger ─────────────────────────────────────────────
    from app.utils.logger import setup_logger, get_logger
    setup_logger()
    logger = get_logger(__name__)

    # ── Startup banner ────────────────────────────────────────────────────────
    logger.info("════════════════════════════════════════════════════")
    logger.info("  🎵  AI Song Lyrics Generator")
    logger.info("  Python  : %s", sys.version.split()[0])
    logger.info("  Port    : %d", args.port)
    logger.info("════════════════════════════════════════════════════")

    # ── Pre-flight checks ─────────────────────────────────────────────────────
    if not _preflight_checks(logger):
        logger.error("Pre-flight checks failed — aborting launch.")
        sys.exit(1)

    # ── Launch Streamlit ──────────────────────────────────────────────────────
    ui_path = Path(__file__).resolve().parent / "app" / "main.py"

    if not ui_path.exists():
        logger.error("UI file not found: %s", ui_path)
        sys.exit(1)

    logger.info("Launching Streamlit UI → %s", ui_path)
    logger.info("Open your browser at:  http://localhost:%d", args.port)
    logger.info("Press Ctrl+C to stop.")

    cmd = [
        sys.executable, "-m", "streamlit", "run", str(ui_path),
        "--server.port", str(args.port),
        "--server.headless", "true",        # don't auto-open browser in CI
        "--logger.level", "warning",        # suppress Streamlit's own verbose logs
    ]

    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        logger.info("Shutdown requested by user (Ctrl+C).")
    except subprocess.CalledProcessError as exc:
        logger.error("Streamlit exited with return code %d.", exc.returncode)
        sys.exit(exc.returncode)
    except FileNotFoundError:
        logger.error(
            "Streamlit is not installed. Run: pip install streamlit"
        )
        sys.exit(1)
    except Exception as exc:
        logger.exception("Unexpected error while launching app: %s", exc)
        sys.exit(1)

    logger.info("Application stopped cleanly.")


# =============================================================================
# 4. PRE-FLIGHT CHECKS
# =============================================================================

def _preflight_checks(logger) -> bool:
    """
    Validate the environment before starting the UI.

    Returns ``True`` if all checks pass, ``False`` if any critical check
    fails.  Non-critical issues log a warning and continue.

    Checks performed
    ----------------
    * Required directories exist (created by config if missing).
    * ``config.py`` values are within expected ranges.
    * Key third-party packages are importable.
    """
    all_ok = True

    logger.info("Running pre-flight checks …")

    # ── Config import ─────────────────────────────────────────────────────────
    try:
        from app import config
    except ImportError as exc:
        logger.error("Cannot import app.config: %s", exc)
        return False

    # ── Required directories ──────────────────────────────────────────────────
    required_dirs = {
        "INPUT_DIR":  config.INPUT_DIR,
        "OUTPUT_DIR": config.OUTPUT_DIR,
        "TEMP_DIR":   config.TEMP_DIR,
    }
    for name, path in required_dirs.items():
        dir_path = Path(path)
        if not dir_path.exists():
            logger.warning("%s missing — creating: %s", name, dir_path)
            try:
                dir_path.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                logger.error("Cannot create %s: %s", name, exc)
                all_ok = False
        else:
            logger.debug("  ✓  %s: %s", name, dir_path)

    # ── config value sanity ───────────────────────────────────────────────────
    if config.MAX_FILE_SIZE_MB <= 0:
        logger.error("MAX_FILE_SIZE_MB must be > 0 (got %s).", config.MAX_FILE_SIZE_MB)
        all_ok = False

    if config.TARGET_SAMPLE_RATE not in (8000, 16000, 22050, 44100, 48000):
        logger.warning(
            "Unusual TARGET_SAMPLE_RATE: %d Hz. Whisper works best at 16000.",
            config.TARGET_SAMPLE_RATE,
        )

    if config.WHISPER_MODEL_SIZE not in ("tiny", "base", "small", "medium", "large"):
        logger.error(
            "Unknown WHISPER_MODEL_SIZE: '%s'. "
            "Valid options: tiny, base, small, medium, large.",
            config.WHISPER_MODEL_SIZE,
        )
        all_ok = False

    # ── Key package availability ──────────────────────────────────────────────
    packages = {
        "streamlit": "streamlit",
        "whisper":   "openai-whisper",
        "pydub":     "pydub",
        "librosa":   "librosa",
        "soundfile": "soundfile",
        "spleeter":  "spleeter",
    }

    for module, pip_name in packages.items():
        try:
            __import__(module)
            logger.debug("  ✓  %s", module)
        except ImportError:
            logger.warning(
                "  ✗  '%s' not installed — run: pip install %s",
                module, pip_name,
            )
            # Don't hard-fail; user may have partial install and want to test UI
            # Only whisper and streamlit are truly critical for startup
            if module in ("streamlit", "whisper"):
                all_ok = False

    # ── Summary ───────────────────────────────────────────────────────────────
    if all_ok:
        logger.info("Pre-flight checks passed ✓")
    else:
        logger.error("One or more pre-flight checks failed — see above.")

    return all_ok


# =============================================================================
# 5. ENTRY POINT GUARD
# =============================================================================

if __name__ == "__main__":
    main()