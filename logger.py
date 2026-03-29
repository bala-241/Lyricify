# =============================================================================
# app/utils/logger.py — Central Logging System
# =============================================================================
# Responsibilities:
#   • Configure the root logger ONCE for the entire application
#   • Output to both console (with colour) and rotating log files
#   • Route ERROR+ logs to a separate error.log for quick triage
#   • Provide get_logger() so every module gets a named child logger
#   • Respect LOG_LEVEL and LOG_FILE from config
#
# Usage (in every module):
#   from app.utils.logger import get_logger
#   logger = get_logger(__name__)
#
# Bootstrap (call ONCE, in main.py or run.py, before anything else):
#   from app.utils.logger import setup_logger
#   setup_logger()
# =============================================================================

# 1. IMPORTS
# =============================================================================
import logging
import logging.handlers
import sys
from pathlib import Path

# Config is imported lazily inside setup_logger() so the module can be
# imported safely even before the app package is fully initialised.

# =============================================================================
# 2. COLOUR SUPPORT  (optional — degrades gracefully if unavailable)
# =============================================================================

try:
    import colorlog as _colorlog
    _HAS_COLORLOG = True
except ImportError:
    _HAS_COLORLOG = False

# =============================================================================
# 3. INTERNAL STATE
# =============================================================================

# Guard flag — setup_logger() is idempotent; calling it multiple times does
# nothing after the first successful call.
_is_configured: bool = False

# =============================================================================
# 4. LOG FORMAT CONSTANTS
# =============================================================================

_PLAIN_FORMAT  = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT   = "%Y-%m-%d %H:%M:%S"

# Colour map used when colorlog is available
_COLOUR_MAP = {
    "DEBUG":    "cyan",
    "INFO":     "green",
    "WARNING":  "yellow",
    "ERROR":    "red",
    "CRITICAL": "bold_red",
}

# =============================================================================
# 5. SETUP FUNCTION
# =============================================================================

def setup_logger() -> None:
    """
    Configure the root Python logger for the entire application.

    Call this **once** at the application entry-point (``main.py`` or
    ``run.py``) before any other module is imported or used.  Subsequent
    calls are silently ignored (idempotent).

    What is configured
    ------------------
    * **Console handler** — coloured output if ``colorlog`` is installed,
      plain text otherwise.  Level controlled by ``config.LOG_LEVEL``.
    * **Rotating file handler** (``config.LOG_FILE``) — plain text, max
      5 MB per file, 3 backup copies.  Keeps log history without filling
      up the disk.
    * **Error file handler** (``error.log`` next to ``config.LOG_FILE``) —
      captures only ``ERROR`` and above for quick triage.

    Log format
    ----------
    ::

        2026-03-29 18:45:21 | INFO     | app.audio_processor | Converted to WAV

    Notes
    -----
    * Silences overly-verbose third-party loggers (``urllib3``,
      ``matplotlib``, ``numba``, ``tensorflow``) so they don't drown out
      application logs.
    * Creates the log file's parent directory if it doesn't exist.
    """
    global _is_configured

    if _is_configured:
        return

    # ── Import config here to avoid circular import at module level ───────────
    from app import config

    log_level  = getattr(logging, str(config.LOG_LEVEL).upper(), logging.INFO)
    log_file   = Path(config.LOG_FILE)
    error_file = log_file.parent / "error.log"

    # ── Ensure log directory exists ───────────────────────────────────────────
    log_file.parent.mkdir(parents=True, exist_ok=True)

    # ── Root logger ───────────────────────────────────────────────────────────
    root = logging.getLogger()
    root.setLevel(log_level)

    # Remove any handlers added by earlier basicConfig calls (e.g. in tests)
    root.handlers.clear()

    plain_formatter = logging.Formatter(_PLAIN_FORMAT, datefmt=_DATE_FORMAT)

    # ── Console handler ───────────────────────────────────────────────────────
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)

    if _HAS_COLORLOG:
        colour_formatter = _colorlog.ColoredFormatter(
            "%(log_color)s" + _PLAIN_FORMAT,
            datefmt=_DATE_FORMAT,
            log_colors=_COLOUR_MAP,
        )
        console_handler.setFormatter(colour_formatter)
    else:
        console_handler.setFormatter(plain_formatter)

    root.addHandler(console_handler)

    # ── Rotating file handler (all levels ≥ LOG_LEVEL) ───────────────────────
    file_handler = logging.handlers.RotatingFileHandler(
        filename=log_file,
        maxBytes=5 * 1024 * 1024,   # 5 MB per file
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(plain_formatter)
    root.addHandler(file_handler)

    # ── Error-only file handler ───────────────────────────────────────────────
    error_handler = logging.handlers.RotatingFileHandler(
        filename=error_file,
        maxBytes=2 * 1024 * 1024,   # 2 MB
        backupCount=2,
        encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(plain_formatter)
    root.addHandler(error_handler)

    # ── Silence noisy third-party loggers ─────────────────────────────────────
    _QUIET_LOGGERS = [
        "urllib3", "matplotlib", "numba",
        "tensorflow", "PIL", "httpx", "httpcore",
    ]
    for name in _QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)

    _is_configured = True

    # Announce configuration using the root logger so the message itself
    # appears in the log file.
    _startup_banner(log_level, log_file, error_file)


# =============================================================================
# 6. GET-LOGGER HELPER
# =============================================================================

def get_logger(name: str) -> logging.Logger:
    """
    Return a named child logger for *name*.

    Always pass ``__name__`` so log messages carry the full module path::

        from app.utils.logger import get_logger
        logger = get_logger(__name__)
        logger.info("Audio converted.")
        # → 2026-03-29 18:45:21 | INFO     | app.audio_processor | Audio converted.

    Parameters
    ----------
    name : str
        Typically ``__name__`` — the fully-qualified module name.

    Returns
    -------
    logging.Logger
        A standard Python logger.  If ``setup_logger()`` has not been
        called yet, the logger still works but output goes only to the
        root handler (usually stderr with no formatting).
    """
    return logging.getLogger(name)


# =============================================================================
# 7. INTERNAL HELPERS
# =============================================================================

def _startup_banner(
    level: int,
    log_file: Path,
    error_file: Path,
) -> None:
    """Log a startup summary so you can tell exactly when the app booted."""
    banner_logger = logging.getLogger("app.logger")
    banner_logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    banner_logger.info("  Logging initialised")
    banner_logger.info("  Level      : %s", logging.getLevelName(level))
    banner_logger.info("  Log file   : %s", log_file)
    banner_logger.info("  Error file : %s", error_file)
    banner_logger.info("  Colour     : %s", "enabled" if _HAS_COLORLOG else "disabled (pip install colorlog)")
    banner_logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")


def reset_logger() -> None:
    """
    Tear down the current logging configuration and reset the guard flag.

    **Testing only** — allows tests to call ``setup_logger()`` with a
    fresh config without restarting the process.
    """
    global _is_configured
    root = logging.getLogger()
    for handler in root.handlers[:]:
        handler.close()
        root.removeHandler(handler)
    _is_configured = False


# =============================================================================
# QUICK SANITY-CHECK  (python app/utils/logger.py)
# =============================================================================
if __name__ == "__main__":
    setup_logger()

    logger = get_logger(__name__)

    logger.debug("DEBUG   — detailed dev info (only visible when LOG_LEVEL=DEBUG)")
    logger.info("INFO    — pipeline step completed normally")
    logger.warning("WARNING — something unusual but not fatal")
    logger.error("ERROR   — something failed, check error.log too")

    # Idempotency check — second call should be a silent no-op
    setup_logger()
    setup_logger()
    logger.info("Called setup_logger() 3× total — still one set of handlers ✓")

    # Child logger test
    child = get_logger("app.audio_processor")
    child.info("Child logger works — module name appears in output ✓")

    from app import config
    print(f"\nLog file   : {config.LOG_FILE}")
    print(f"Error file : {Path(config.LOG_FILE).parent / 'error.log'}")
    print("\n✅  logger self-check complete.")