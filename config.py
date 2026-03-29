# =============================================================================
# app/config.py — Central Control Panel
# =============================================================================

# 1. IMPORTS
# =============================================================================
import os
from pathlib import Path

# =============================================================================
# 2. BASE PATHS
# =============================================================================

# Root of the project (two levels up from this file: app/ → project root)
BASE_DIR = Path(__file__).resolve().parent.parent

# Data directories
DATA_DIR  = BASE_DIR / "data"
INPUT_DIR = DATA_DIR / "input"   # uploaded audio files
OUTPUT_DIR= DATA_DIR / "output"  # generated lyrics / transcripts
TEMP_DIR  = DATA_DIR / "temp"    # intermediate files (vocals.wav, etc.)

# Auto-create directories if they don't exist
for _dir in (INPUT_DIR, OUTPUT_DIR, TEMP_DIR):
    _dir.mkdir(parents=True, exist_ok=True)

# =============================================================================
# 3. AUDIO SETTINGS
# =============================================================================

SUPPORTED_FORMATS   = ["mp3", "wav", "flac"]   # file types accepted upstream
TARGET_SAMPLE_RATE  = 16_000                    # Hz — optimal for Whisper
AUDIO_CHANNELS      = 1                         # 1 = mono (best for ASR models)

# =============================================================================
# 4. MODEL SETTINGS  (Whisper)
# =============================================================================

# Options: "tiny" | "base" | "small" | "medium" | "large"
# Larger  → better accuracy, slower inference
WHISPER_MODEL_SIZE  = "base"

# "cpu" for most machines; swap to "cuda" when a GPU is available
DEVICE              = "cuda" if os.environ.get("USE_CUDA") == "1" else "cpu"

# =============================================================================
# 5. VOCAL SEPARATION SETTINGS  (Spleeter)
# =============================================================================

# "spleeter:2stems"  → vocals + instrumental  ✓  (all we need)
# "spleeter:4stems"  → vocals / drums / bass / other
# "spleeter:5stems"  → vocals / drums / bass / piano / other
SPLEETER_MODEL      = "spleeter:2stems"

# =============================================================================
# 6. FILE VALIDATION
# =============================================================================

MAX_FILE_SIZE_MB    = 20                        # reject uploads larger than this
ALLOWED_EXTENSIONS  = ["mp3", "wav"]            # stricter than SUPPORTED_FORMATS

def is_allowed_file(filename: str) -> bool:
    """Return True if *filename* has an accepted extension."""
    ext = Path(filename).suffix.lstrip(".").lower()
    return ext in ALLOWED_EXTENSIONS

def is_allowed_size(filepath: str | Path) -> bool:
    """Return True if the file at *filepath* is within the size limit."""
    size_mb = Path(filepath).stat().st_size / (1024 * 1024)
    return size_mb <= MAX_FILE_SIZE_MB

# =============================================================================
# 7. LOGGING SETTINGS
# =============================================================================

LOG_LEVEL           = "INFO"                    # DEBUG | INFO | WARNING | ERROR
LOG_FILE            = BASE_DIR / "app.log"      # set to None to disable file log

# =============================================================================
# 8. PERFORMANCE SETTINGS
# =============================================================================

USE_GPU             = DEVICE == "cuda"          # derived from DEVICE (single source of truth)
BATCH_SIZE          = 1                         # increase for GPU batch inference

# =============================================================================
# 9. DEVELOPMENT FLAGS
# =============================================================================

DEBUG                    = True    # verbose output, extra checks
SAVE_INTERMEDIATE_FILES  = True    # keep temp vocals.wav during development
                                   # set False in production to save disk space

# =============================================================================
# 10. FUTURE-READY PLACEHOLDERS
# =============================================================================

API_KEYS            = {}           # e.g. {"genius": "...", "spotify": "..."}
DATABASE_URL        = None         # e.g. "sqlite:///lyrics.db"


# =============================================================================
# QUICK SANITY-CHECK  (python app/config.py)
# =============================================================================
if __name__ == "__main__":
    print("=== Project Paths ===")
    print(f"  BASE_DIR   : {BASE_DIR}")
    print(f"  INPUT_DIR  : {INPUT_DIR}")
    print(f"  OUTPUT_DIR : {OUTPUT_DIR}")
    print(f"  TEMP_DIR   : {TEMP_DIR}")
    print("\n=== Audio ===")
    print(f"  Sample rate : {TARGET_SAMPLE_RATE} Hz | Channels : {AUDIO_CHANNELS}")
    print(f"  Formats     : {SUPPORTED_FORMATS}")
    print("\n=== Models ===")
    print(f"  Whisper     : {WHISPER_MODEL_SIZE} on {DEVICE}")
    print(f"  Spleeter    : {SPLEETER_MODEL}")
    print("\n=== Limits ===")
    print(f"  Max size    : {MAX_FILE_SIZE_MB} MB | Allowed : {ALLOWED_EXTENSIONS}")
    print("\n=== Dev Flags ===")
    print(f"  DEBUG={DEBUG}  SAVE_INTERMEDIATE={SAVE_INTERMEDIATE_FILES}")