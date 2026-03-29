# =============================================================================
# app/text_cleaner.py — Lyrics Post-Processing & Formatting
# =============================================================================
# Responsibilities:
#   • Strip noise, artefacts, and filler from raw Whisper output
#   • Remove unintentional word/phrase repetition
#   • Format cleaned text into readable, line-broken lyrics
#   • Clean and merge timestamped segments
#   • Orchestrate the full clean → format pipeline via process_text()
#
# Pipeline position:
#   transcriber.py  →  text_cleaner.py  →  final output / UI
#
# Design principles:
#   • Every function does ONE job and is independently reusable
#   • Original data is never mutated — always return new strings/objects
#   • Balance cleaning vs artistic intent (intentional repetition is kept)
#   • Safe for non-English text — no ASCII-only assumptions
# =============================================================================

# 1. IMPORTS
# =============================================================================
import logging
import re
from typing import Any

# =============================================================================
# 2. MODULE LOGGER
# =============================================================================

logger = logging.getLogger(__name__)

# =============================================================================
# 3. CONSTANTS
# =============================================================================

# Filler words / non-lyric noise commonly hallucinated by Whisper or sung as
# placeholder sounds.  All comparisons are case-insensitive.
_FILLER_WORDS = {
    "uh", "um", "ah", "er", "hmm", "hm", "mhm",
    "uhh", "umm", "ahh", "err",
}

# Whisper sometimes emits these meta-tokens for non-speech audio.
# We strip them before any other processing.
_WHISPER_ARTEFACTS = re.compile(
    r"\[(?:Music|Applause|Laughter|Silence|Noise|Inaudible|.*?)\]",
    flags=re.IGNORECASE,
)

# Punctuation characters that are natural line-break candidates in lyrics.
_LINE_BREAK_PUNCT = re.compile(r"(?<=[.!?,;:])\s+")

# Minimum duration (seconds) for a segment to be kept on its own.
# Segments shorter than this are merged into the next one.
_MIN_SEGMENT_DURATION = 0.5

# Maximum words per lyrics line before a forced break is inserted.
_MAX_WORDS_PER_LINE = 8


# =============================================================================
# 4. STEP 1 — BASIC TEXT CLEANING
# =============================================================================

def clean_text(raw_text: str) -> str:
    """
    Apply foundational cleaning to *raw_text*.

    Operations (in order)
    ---------------------
    1. Strip Whisper meta-tokens  (``[Music]``, ``[Applause]``, …)
    2. Remove filler words        (``uh``, ``um``, ``ah``, …)
    3. Collapse multiple spaces   → single space
    4. Strip leading/trailing whitespace
    5. Capitalise the first letter of the result

    Parameters
    ----------
    raw_text : str
        The ``text`` field directly from ``transcriber.transcribe_audio()``.

    Returns
    -------
    str
        Lightly cleaned text, ready for repetition removal.

    Examples
    --------
    >>> clean_text("[Music] uh hello   world  ah")
    'Hello world'
    """
    if not raw_text or not raw_text.strip():
        logger.debug("clean_text() received empty input — returning empty string.")
        return ""

    text = raw_text

    # 1. Remove Whisper artefact tokens
    text = _WHISPER_ARTEFACTS.sub(" ", text)

    # 2. Remove filler words (whole-word match, case-insensitive)
    filler_pattern = re.compile(
        r"\b(?:" + "|".join(re.escape(w) for w in _FILLER_WORDS) + r")\b[,.]?",
        flags=re.IGNORECASE,
    )
    text = filler_pattern.sub(" ", text)

    # 3. Collapse runs of whitespace (including newlines) → single space
    text = re.sub(r"\s+", " ", text)

    # 4. Strip
    text = text.strip()

    # 5. Capitalise first character without lowercasing the rest
    if text:
        text = text[0].upper() + text[1:]

    logger.debug("clean_text() → %d chars", len(text))
    return text


# =============================================================================
# 5. STEP 2 — REPETITION REMOVAL
# =============================================================================

def remove_repetition(text: str) -> str:
    """
    Remove *unintentional* consecutive word and phrase repetitions.

    Strategy
    --------
    * **Word-level** : deduplicate immediately adjacent identical words
      (e.g. ``"baby baby"`` → ``"baby"``).
    * **Phrase-level** : detect runs of 2–4 word phrases repeated back-to-back
      three or more times and collapse them to two occurrences — preserving the
      artistic feel of a chorus while eliminating transcript artefacts.

    Why keep two occurrences for phrase repeats?
      A single repeat (``"baby baby"``) is extremely common stylistically.
      Three or more consecutive identical phrases are almost always a
      Whisper hallucination or transcription stutter.

    Parameters
    ----------
    text : str
        Output of :func:`clean_text`.

    Returns
    -------
    str
        Text with artefactual repetition collapsed.

    Examples
    --------
    >>> remove_repetition("hello hello world")
    'hello world'
    >>> remove_repetition("never gonna never gonna never gonna give you up")
    'never gonna never gonna give you up'
    """
    if not text:
        return ""

    # ── Word-level dedup ──────────────────────────────────────────────────────
    # Replace 2+ consecutive identical words (case-insensitive) with one copy.
    # Preserves original casing of the kept word.
    word_dedup = re.compile(r"\b(\w+)(?:\s+\1){1,}\b", flags=re.IGNORECASE)

    def _keep_first(match: re.Match) -> str:
        return match.group(1)

    text = word_dedup.sub(_keep_first, text)

    # ── Phrase-level dedup (2–4 words, 3+ repeats → 2 repeats) ───────────────
    for phrase_len in range(4, 1, -1):          # try longer phrases first
        pattern = re.compile(
            r"\b((?:\w+\s+){" + str(phrase_len - 1) + r"}\w+)"
            r"(?:\s+\1){2,}\b",
            flags=re.IGNORECASE,
        )

        def _keep_two(match: re.Match) -> str:
            phrase = match.group(1)
            return f"{phrase} {phrase}"

        text = pattern.sub(_keep_two, text)

    # Re-collapse any whitespace introduced by substitutions
    text = re.sub(r"\s+", " ", text).strip()

    logger.debug("remove_repetition() → %d chars", len(text))
    return text


# =============================================================================
# 6. STEP 3 — LYRICS FORMATTING
# =============================================================================

def format_lyrics(text: str) -> str:
    """
    Transform a cleaned, continuous string into line-broken lyrics.

    Line-breaking strategy (applied in priority order)
    --------------------------------------------------
    1. Natural breaks after sentence-ending punctuation (``.``, ``!``, ``?``).
    2. Natural breaks after phrase punctuation (``,``, ``;``, ``:``).
    3. Forced break every ``_MAX_WORDS_PER_LINE`` words when no punctuation
       break occurs within the window.

    Additional formatting
    ---------------------
    * Each line is capitalised.
    * Trailing whitespace is stripped from every line.
    * Consecutive blank lines are collapsed to one.

    Parameters
    ----------
    text : str
        Output of :func:`remove_repetition`.

    Returns
    -------
    str
        Multi-line lyrics string, ready for display or file output.

    Examples
    --------
    >>> format_lyrics("hello world how are you doing today my friend")
    'Hello world how are you\\ndoing today my friend'
    """
    if not text:
        return ""

    # ── 1. Break on punctuation ───────────────────────────────────────────────
    text = _LINE_BREAK_PUNCT.sub("\n", text)

    # ── 2. Forced break every N words within long lines ───────────────────────
    output_lines: list[str] = []

    for raw_line in text.splitlines():
        raw_line = raw_line.strip()
        if not raw_line:
            continue

        words = raw_line.split()

        if len(words) <= _MAX_WORDS_PER_LINE:
            output_lines.append(raw_line)
        else:
            # Chunk into groups of at most _MAX_WORDS_PER_LINE
            chunks = [
                words[i : i + _MAX_WORDS_PER_LINE]
                for i in range(0, len(words), _MAX_WORDS_PER_LINE)
            ]
            output_lines.extend(" ".join(chunk) for chunk in chunks)

    # ── 3. Capitalise each line & strip trailing spaces ───────────────────────
    formatted: list[str] = []
    for line in output_lines:
        line = line.strip()
        if line:
            line = line[0].upper() + line[1:]
            formatted.append(line)

    # ── 4. Collapse consecutive blank lines ───────────────────────────────────
    lyrics = "\n".join(formatted)
    lyrics = re.sub(r"\n{3,}", "\n\n", lyrics).strip()

    logger.debug("format_lyrics() → %d lines", len(formatted))
    return lyrics


# =============================================================================
# 7. STEP 4 — SEGMENT CLEANING
# =============================================================================

def clean_segments(segments: list[dict]) -> list[dict]:
    """
    Clean and optionally merge Whisper timestamp segments.

    Operations
    ----------
    * Drop segments with empty text.
    * Apply :func:`clean_text` and :func:`remove_repetition` to each segment's
      text.
    * Merge consecutive segments whose *individual* duration is less than
      ``_MIN_SEGMENT_DURATION`` seconds into the following segment.
    * Re-index segment IDs sequentially after merging.

    Parameters
    ----------
    segments : list[dict]
        The ``segments`` list from ``transcriber.transcribe_audio()``, where
        each item contains at minimum ``start``, ``end``, and ``text``.

    Returns
    -------
    list[dict]
        Cleaned, merged list of segment dicts — same shape as input.

    Notes
    -----
    Empty input returns an empty list without raising.
    """
    if not segments:
        logger.debug("clean_segments() received empty list.")
        return []

    cleaned: list[dict] = []

    for seg in segments:
        text = clean_text(seg.get("text", ""))
        text = remove_repetition(text)

        if not text:
            logger.debug("Dropping empty segment id=%s.", seg.get("id"))
            continue

        cleaned.append({
            "id":    seg.get("id"),
            "start": seg.get("start", 0.0),
            "end":   seg.get("end",   0.0),
            "text":  text,
        })

    # ── Merge very short segments into the next one ───────────────────────────
    merged: list[dict] = []

    i = 0
    while i < len(cleaned):
        seg = cleaned[i]
        duration = seg["end"] - seg["start"]

        if duration < _MIN_SEGMENT_DURATION and i + 1 < len(cleaned):
            next_seg = cleaned[i + 1]
            # Absorb this segment into the next
            merged.append({
                "id":    next_seg["id"],
                "start": seg["start"],            # extend start backward
                "end":   next_seg["end"],
                "text":  f"{seg['text']} {next_seg['text']}".strip(),
            })
            i += 2                                # skip next (already merged)
        else:
            merged.append(seg)
            i += 1

    # ── Re-index ──────────────────────────────────────────────────────────────
    for idx, seg in enumerate(merged):
        seg["id"] = idx

    logger.debug(
        "clean_segments() — %d in → %d out (merged %d short).",
        len(segments),
        len(merged),
        len(segments) - len(merged),
    )
    return merged


# =============================================================================
# 8. MAIN PIPELINE — process_text()
# =============================================================================

def process_text(transcription_result: dict[str, Any]) -> dict[str, Any]:
    """
    Run the complete text-cleaning pipeline on a transcription result dict.

    Accepts the dict returned by ``transcriber.transcribe_audio()`` and
    returns an enriched dict that is ready for display, file saving, or
    further downstream processing.

    Pipeline
    --------
    clean_text()  →  remove_repetition()  →  format_lyrics()
                 →  clean_segments()      →  return result

    Parameters
    ----------
    transcription_result : dict
        Must contain at minimum:

        * ``"text"``     — raw transcript string
        * ``"segments"`` — list of timed segment dicts
        * ``"language"`` — ISO 639-1 language code

        Optional keys forwarded unchanged: ``"model_size"``,
        ``"word_count"``, ``"segment_count"``.

    Returns
    -------
    dict with keys
    ──────────────
    original_text  : str   — raw Whisper output, untouched
    cleaned_text   : str   — after clean_text() + remove_repetition()
    lyrics         : str   — after format_lyrics() (multi-line)
    segments       : list  — after clean_segments()
    language       : str   — from input (unchanged)
    word_count     : int   — word count of *cleaned_text*
    segment_count  : int   — length of cleaned segments list
    model_size     : str   — from input (unchanged)

    Raises
    ------
    TypeError
        If *transcription_result* is not a dict.
    KeyError
        If required key ``"text"`` is missing.

    Example
    -------
    >>> from app.transcriber import transcribe_audio
    >>> raw = transcribe_audio("data/temp/vocals.wav")
    >>> final = process_text(raw)
    >>> print(final["lyrics"])
    """
    logger.info("━━━  Text cleaning pipeline started  ━━━")

    # ── Guard inputs ──────────────────────────────────────────────────────────
    if not isinstance(transcription_result, dict):
        raise TypeError(
            f"process_text() expects a dict, got {type(transcription_result).__name__}."
        )

    raw_text = transcription_result.get("text")
    if raw_text is None:
        raise KeyError(
            "'text' key is missing from transcription_result. "
            "Pass the dict returned by transcriber.transcribe_audio()."
        )

    segments  = transcription_result.get("segments",  [])
    language  = transcription_result.get("language",  "unknown")
    model_sz  = transcription_result.get("model_size", "unknown")

    # ── Step 1: basic cleaning ────────────────────────────────────────────────
    logger.info("Cleaning raw text …")
    cleaned = clean_text(raw_text)

    # ── Step 2: remove artefactual repetition ─────────────────────────────────
    logger.info("Removing repetition …")
    deduped = remove_repetition(cleaned)

    # ── Step 3: format as lyrics ──────────────────────────────────────────────
    logger.info("Formatting lyrics …")
    lyrics = format_lyrics(deduped)

    # ── Step 4: clean segments ────────────────────────────────────────────────
    logger.info("Cleaning segments …")
    clean_segs = clean_segments(segments)

    # ── Assemble result ───────────────────────────────────────────────────────
    result: dict[str, Any] = {
        "original_text":  raw_text,
        "cleaned_text":   deduped,
        "lyrics":         lyrics,
        "segments":       clean_segs,
        "language":       language,
        "word_count":     len(deduped.split()) if deduped else 0,
        "segment_count":  len(clean_segs),
        "model_size":     model_sz,
    }

    logger.info(
        "Pipeline complete — %d word(s), %d segment(s), %d lyric line(s).",
        result["word_count"],
        result["segment_count"],
        len(lyrics.splitlines()),
    )
    logger.info("━━━  Text cleaning done  ━━━")

    return result


# =============================================================================
# QUICK SANITY-CHECK  (python app/text_cleaner.py)
# =============================================================================
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(levelname)-8s │ %(name)s │ %(message)s",
    )

    # ── clean_text ────────────────────────────────────────────────────────────
    print("=== clean_text() ===")
    samples = [
        "[Music] uh hello   world  ah",
        "um this is a test um of the system",
        "",
        "[Applause] thank you thank you very much",
    ]
    for s in samples:
        print(f"  {s!r:50s} → {clean_text(s)!r}")

    # ── remove_repetition ─────────────────────────────────────────────────────
    print("\n=== remove_repetition() ===")
    reps = [
        "baby baby baby oh",
        "never gonna never gonna never gonna give you up",
        "hello hello world world",
        "I love you I love you I love you so much",
    ]
    for r in reps:
        print(f"  {r!r:55s} → {remove_repetition(r)!r}")

    # ── format_lyrics ─────────────────────────────────────────────────────────
    print("\n=== format_lyrics() ===")
    prose = (
        "hello world how are you doing today my friend, "
        "I hope everything is going well. stay strong!"
    )
    print(f"  Input : {prose!r}")
    print("  Output:")
    for line in format_lyrics(prose).splitlines():
        print(f"    {line}")

    # ── clean_segments ────────────────────────────────────────────────────────
    print("\n=== clean_segments() ===")
    segs = [
        {"id": 0, "start": 0.0, "end": 0.2, "text": "uh"},           # short + filler
        {"id": 1, "start": 0.2, "end": 3.5, "text": "hello world"},
        {"id": 2, "start": 3.5, "end": 3.8, "text": ""},              # empty
        {"id": 3, "start": 3.8, "end": 7.0, "text": "baby baby baby oh baby"},
    ]
    for s in clean_segments(segs):
        print(f"  [{s['start']:.1f}–{s['end']:.1f}s] {s['text']!r}")

    # ── process_text (full pipeline) ──────────────────────────────────────────
    print("\n=== process_text() ===")
    mock_transcription = {
        "text":          "[Music] uh never gonna give you up never gonna let you down never gonna run around and desert you",
        "segments":      segs,
        "language":      "en",
        "word_count":    20,
        "segment_count": 4,
        "model_size":    "base",
    }
    result = process_text(mock_transcription)
    print(f"  language      : {result['language']}")
    print(f"  word_count    : {result['word_count']}")
    print(f"  segment_count : {result['segment_count']}")
    print(f"  cleaned_text  : {result['cleaned_text']!r}")
    print("  lyrics:")
    for line in result["lyrics"].splitlines():
        print(f"    {line}")

    print("\n✅  text_cleaner self-check complete.")