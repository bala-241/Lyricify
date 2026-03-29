# =============================================================================
# main.py — Streamlit Frontend (UI Layer)
# =============================================================================
# Responsibilities:
#   • Provide a clean, polished interface for uploading audio
#   • Trigger the full pipeline via process_upload()
#   • Display lyrics, metadata, timestamps, and download options
#   • Never crash — all error states are handled gracefully
#
# Run with:
#   streamlit run main.py
# =============================================================================

import streamlit as st
from app.routes.upload import process_upload

# =============================================================================
# PAGE CONFIG  (must be the very first Streamlit call)
# =============================================================================

st.set_page_config(
    page_title="Lyricify — AI Lyrics Generator",
    page_icon="🎵",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# =============================================================================
# CUSTOM CSS — dark editorial aesthetic, warm amber accents
# =============================================================================

st.markdown("""
<style>
/* ── Google Fonts ─────────────────────────────────────────────────────── */
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;700;900&family=DM+Mono:wght@300;400;500&family=DM+Sans:wght@300;400;500&display=swap');

/* ── CSS Variables ────────────────────────────────────────────────────── */
:root {
    --bg:          #0d0d0d;
    --surface:     #161616;
    --border:      #2a2a2a;
    --accent:      #f0a500;
    --accent-dim:  #f0a50022;
    --text-primary:#f5f0e8;
    --text-muted:  #7a7570;
    --success:     #4ade80;
    --error:       #f87171;
    --radius:      12px;
}

/* ── Base ─────────────────────────────────────────────────────────────── */
html, body, [data-testid="stAppViewContainer"] {
    background-color: var(--bg) !important;
    color: var(--text-primary) !important;
    font-family: 'DM Sans', sans-serif;
}

[data-testid="stHeader"] { background: transparent !important; }
[data-testid="stToolbar"] { display: none; }
.block-container { max-width: 760px; padding: 2rem 1.5rem 4rem; }

/* ── Typography ───────────────────────────────────────────────────────── */
h1, h2, h3 { font-family: 'Playfair Display', serif !important; }

/* ── Hero title ───────────────────────────────────────────────────────── */
.hero-title {
    font-family: 'Playfair Display', serif;
    font-size: clamp(2.6rem, 6vw, 4rem);
    font-weight: 900;
    line-height: 1.05;
    letter-spacing: -0.03em;
    color: var(--text-primary);
    margin: 0 0 0.35rem;
}
.hero-title span { color: var(--accent); }
.hero-sub {
    font-family: 'DM Mono', monospace;
    font-size: 0.8rem;
    font-weight: 300;
    color: var(--text-muted);
    letter-spacing: 0.15em;
    text-transform: uppercase;
    margin-bottom: 2.5rem;
}

/* ── Upload area ─────────────────────────────────────────────────────── */
[data-testid="stFileUploader"] {
    background: var(--surface) !important;
    border: 1.5px dashed var(--border) !important;
    border-radius: var(--radius) !important;
    padding: 1rem !important;
    transition: border-color 0.2s;
}
[data-testid="stFileUploader"]:hover {
    border-color: var(--accent) !important;
}
[data-testid="stFileUploader"] label {
    color: var(--text-muted) !important;
    font-family: 'DM Mono', monospace !important;
    font-size: 0.8rem !important;
}

/* ── Primary button ───────────────────────────────────────────────────── */
.stButton > button {
    width: 100%;
    background: var(--accent) !important;
    color: #0d0d0d !important;
    font-family: 'DM Mono', monospace !important;
    font-weight: 500 !important;
    font-size: 0.82rem !important;
    letter-spacing: 0.12em !important;
    text-transform: uppercase !important;
    border: none !important;
    border-radius: 6px !important;
    padding: 0.75rem 2rem !important;
    transition: opacity 0.15s, transform 0.1s !important;
}
.stButton > button:hover {
    opacity: 0.88 !important;
    transform: translateY(-1px) !important;
}
.stButton > button:active { transform: translateY(0) !important; }

/* ── Download button (secondary style) ───────────────────────────────── */
.stDownloadButton > button {
    background: transparent !important;
    color: var(--accent) !important;
    border: 1.5px solid var(--accent) !important;
    font-family: 'DM Mono', monospace !important;
    font-size: 0.78rem !important;
    letter-spacing: 0.1em !important;
    text-transform: uppercase !important;
    border-radius: 6px !important;
    padding: 0.55rem 1.4rem !important;
    transition: background 0.15s !important;
}
.stDownloadButton > button:hover {
    background: var(--accent-dim) !important;
}

/* ── Stat cards ───────────────────────────────────────────────────────── */
.stat-row {
    display: flex;
    gap: 0.75rem;
    margin: 1.5rem 0;
    flex-wrap: wrap;
}
.stat-card {
    flex: 1;
    min-width: 110px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 1rem 1.2rem;
}
.stat-label {
    font-family: 'DM Mono', monospace;
    font-size: 0.68rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--text-muted);
    margin-bottom: 0.3rem;
}
.stat-value {
    font-family: 'Playfair Display', serif;
    font-size: 1.6rem;
    font-weight: 700;
    color: var(--accent);
    line-height: 1;
}
.stat-unit {
    font-family: 'DM Sans', sans-serif;
    font-size: 0.75rem;
    color: var(--text-muted);
    margin-top: 0.2rem;
}

/* ── Lyrics block ─────────────────────────────────────────────────────── */
.lyrics-container {
    background: var(--surface);
    border: 1px solid var(--border);
    border-left: 3px solid var(--accent);
    border-radius: var(--radius);
    padding: 2rem 2.2rem;
    margin: 1rem 0 1.5rem;
}
.lyrics-line {
    font-family: 'Playfair Display', serif;
    font-size: 1.05rem;
    line-height: 1.9;
    color: var(--text-primary);
    letter-spacing: 0.01em;
}
.lyrics-line:empty { height: 0.9rem; }

/* ── Segment rows ─────────────────────────────────────────────────────── */
.segment-row {
    display: flex;
    align-items: baseline;
    gap: 1rem;
    padding: 0.55rem 0;
    border-bottom: 1px solid var(--border);
    font-size: 0.88rem;
}
.segment-row:last-child { border-bottom: none; }
.seg-time {
    font-family: 'DM Mono', monospace;
    font-size: 0.72rem;
    color: var(--accent);
    min-width: 110px;
    flex-shrink: 0;
}
.seg-text { color: var(--text-primary); }

/* ── Steps pill list ──────────────────────────────────────────────────── */
.steps-row { display: flex; gap: 0.5rem; flex-wrap: wrap; margin: 0.75rem 0; }
.step-pill {
    font-family: 'DM Mono', monospace;
    font-size: 0.68rem;
    letter-spacing: 0.08em;
    background: var(--accent-dim);
    color: var(--accent);
    border: 1px solid var(--accent);
    border-radius: 99px;
    padding: 0.2rem 0.75rem;
}

/* ── Success / error banners ─────────────────────────────────────────── */
.stAlert { border-radius: var(--radius) !important; }

/* ── Divider ─────────────────────────────────────────────────────────── */
hr { border-color: var(--border) !important; margin: 1.5rem 0 !important; }

/* ── Expander ─────────────────────────────────────────────────────────── */
[data-testid="stExpander"] {
    background: var(--surface) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius) !important;
}
[data-testid="stExpander"] summary {
    font-family: 'DM Mono', monospace !important;
    font-size: 0.8rem !important;
    color: var(--text-muted) !important;
    letter-spacing: 0.08em !important;
}

/* ── Spinner ─────────────────────────────────────────────────────────── */
[data-testid="stSpinner"] p {
    font-family: 'DM Mono', monospace !important;
    font-size: 0.8rem !important;
    color: var(--text-muted) !important;
    letter-spacing: 0.1em !important;
}

/* ── Hide default Streamlit footer ────────────────────────────────────── */
footer { visibility: hidden; }
</style>
""", unsafe_allow_html=True)


# =============================================================================
# HERO HEADER
# =============================================================================

st.markdown("""
<div>
    <div class="hero-title">Lyric<span>ify</span></div>
    <div class="hero-sub">AI · Song → Lyrics · Powered by Whisper + Spleeter</div>
</div>
""", unsafe_allow_html=True)

# =============================================================================
# FILE UPLOAD
# =============================================================================

uploaded_file = st.file_uploader(
    "Drop your audio file here",
    type=["mp3", "wav"],
    help="Supported formats: MP3, WAV · Max size: 20 MB",
    label_visibility="visible",
)

# =============================================================================
# GENERATE BUTTON  (pipeline only runs on click)
# =============================================================================

generate_clicked = st.button("⟶  Generate Lyrics", use_container_width=True)

# =============================================================================
# PIPELINE EXECUTION
# =============================================================================

if generate_clicked:

    # Guard: ensure a file was actually uploaded
    if uploaded_file is None:
        st.warning("Please upload an audio file before generating lyrics.")
        st.stop()

    # ── Run pipeline ──────────────────────────────────────────────────────────
    with st.spinner("Processing your track — this may take a minute …"):
        result = process_upload(uploaded_file)

    st.divider()

    # ── SUCCESS PATH ──────────────────────────────────────────────────────────
    if result["success"]:
        data = result["data"]

        st.success("✓  Lyrics generated successfully", icon=None)

        # ── Stat cards ────────────────────────────────────────────────────────
        lang_display = data.get("language", "—").upper()
        words        = data.get("word_count", 0)
        segments     = data.get("segment_count", 0)
        proc_time    = result.get("processing_time", 0)

        st.markdown(f"""
        <div class="stat-row">
            <div class="stat-card">
                <div class="stat-label">Language</div>
                <div class="stat-value">{lang_display}</div>
                <div class="stat-unit">detected</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Words</div>
                <div class="stat-value">{words:,}</div>
                <div class="stat-unit">in transcript</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Segments</div>
                <div class="stat-value">{segments}</div>
                <div class="stat-unit">timed lines</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Time</div>
                <div class="stat-value">{proc_time:.1f}<span style="font-size:1rem">s</span></div>
                <div class="stat-unit">processing</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # ── Lyrics ────────────────────────────────────────────────────────────
        st.markdown("#### Lyrics")

        lyrics = data.get("lyrics", "")
        lines  = lyrics.splitlines()

        lines_html = "\n".join(
            f'<div class="lyrics-line">{line if line.strip() else "&nbsp;"}</div>'
            for line in lines
        )
        st.markdown(
            f'<div class="lyrics-container">{lines_html}</div>',
            unsafe_allow_html=True,
        )

        # ── Download ──────────────────────────────────────────────────────────
        st.download_button(
            label="↓  Download lyrics.txt",
            data=lyrics,
            file_name="lyrics.txt",
            mime="text/plain",
        )

        st.divider()

        # ── Timestamps expander ───────────────────────────────────────────────
        with st.expander("▸  Show timed segments"):
            segments_data = data.get("segments", [])
            if segments_data:
                rows_html = "\n".join(
                    f"""<div class="segment-row">
                        <span class="seg-time">{seg['start']:.1f}s — {seg['end']:.1f}s</span>
                        <span class="seg-text">{seg['text']}</span>
                    </div>"""
                    for seg in segments_data
                )
                st.markdown(rows_html, unsafe_allow_html=True)
            else:
                st.markdown(
                    '<span style="font-family:\'DM Mono\',monospace;'
                    'font-size:0.8rem;color:var(--text-muted)">No segments available.</span>',
                    unsafe_allow_html=True,
                )

        # ── Pipeline steps ────────────────────────────────────────────────────
        with st.expander("▸  Pipeline steps completed"):
            pills = "".join(
                f'<span class="step-pill">{step.replace("_", " ")}</span>'
                for step in result.get("steps_completed", [])
            )
            st.markdown(
                f'<div class="steps-row">{pills}</div>',
                unsafe_allow_html=True,
            )
            model = data.get("model_size", "—")
            st.markdown(
                f'<span style="font-family:\'DM Mono\',monospace;font-size:0.75rem;'
                f'color:var(--text-muted)">Whisper model: {model}</span>',
                unsafe_allow_html=True,
            )

    # ── FAILURE PATH ──────────────────────────────────────────────────────────
    else:
        error   = result.get("error", {})
        stage   = error.get("stage",   "unknown stage")
        message = error.get("message", "An unexpected error occurred.")

        st.error(f"✗  Pipeline failed at: **{stage.replace('_', ' ').title()}**")

        st.markdown(f"""
        <div style="
            background: #1a0a0a;
            border: 1px solid #3d1515;
            border-left: 3px solid var(--error);
            border-radius: var(--radius);
            padding: 1rem 1.4rem;
            font-family: 'DM Mono', monospace;
            font-size: 0.8rem;
            color: #f87171;
            margin: 0.75rem 0;
            word-break: break-word;
        ">{message}</div>
        """, unsafe_allow_html=True)

        # Show partial progress if any steps completed before the failure
        completed = result.get("steps_completed", [])
        if completed:
            pills = "".join(
                f'<span class="step-pill">{step.replace("_", " ")}</span>'
                for step in completed
            )
            st.markdown("**Steps completed before failure:**")
            st.markdown(
                f'<div class="steps-row">{pills}</div>',
                unsafe_allow_html=True,
            )

        st.markdown(
            '<span style="font-family:\'DM Mono\',monospace;font-size:0.75rem;'
            'color:var(--text-muted)">Check the terminal / app.log for the full traceback.</span>',
            unsafe_allow_html=True,
        )

# =============================================================================
# IDLE STATE  (nothing uploaded yet)
# =============================================================================

elif not generate_clicked:
    st.markdown("""
    <div style="
        text-align: center;
        padding: 2.5rem 1rem;
        font-family: 'DM Mono', monospace;
        font-size: 0.78rem;
        letter-spacing: 0.1em;
        color: #3a3530;
        text-transform: uppercase;
    ">Upload a track · click generate · get lyrics</div>
    """, unsafe_allow_html=True)