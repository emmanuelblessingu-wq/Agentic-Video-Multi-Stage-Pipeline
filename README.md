# Lecture deck → narrated video pipeline

Python pipeline that turns a PDF slide deck into one narrated `.mp4`: rasterized slide images, multimodal agents for descriptions / premise / arc / narration (grounded in a **transcript-derived style profile**), text-to-speech per slide, and **ffmpeg** mux + concat. Intended for local runs; **do not commit** generated images, audio, or video (see `.gitignore`).

## Prerequisites

- **Python 3.10+** (tested with 3.10–3.12; newer versions may work)
- **ffmpeg** on your `PATH` (required for MP3 conversion from Gemini TTS WAV and for final video)
- **Google AI API key** for Gemini (agents use vision + JSON): set `GOOGLE_API_KEY` or `GEMINI_API_KEY`
- Optional: **ElevenLabs** API key (`ELEVENLABS_API_KEY`) for higher-quality TTS; optional voice id `ELEVENLABS_VOICE_ID`

## Repository layout (assignment)

```text
your-repo/
├── README.md
├── style.json                 # produced from transcript (or commit a generated copy)
├── Lecture_17_AI_screenplays.pdf   # add this at repo root for the grader
├── Lecture_17_transcript.txt       # add transcript for style extraction
├── requirements.txt
├── run_lecture_pipeline.py
├── lecture_agents/
└── projects/
    └── project_YYYYMMDD_HHMMSS/
        ├── premise.json
        ├── arc.json
        ├── slide_description.json
        ├── slide_description_narration.json
        ├── slide_images/      # generated; gitignored
        ├── audio/             # generated; gitignored
        └── Lecture_17_AI_screenplays.mp4   # generated; gitignored
```

Place **`Lecture_17_AI_screenplays.pdf`** and a plain-text **`Lecture_17_transcript.txt`** (or pass `--transcript`) in the repo root before running.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Environment variables

| Variable | Purpose |
|----------|---------|
| `GOOGLE_API_KEY` or `GEMINI_API_KEY` | Required for all Gemini agent steps |
| `GEMINI_AGENT_MODEL` | Optional; default `gemini-2.0-flash` |
| `LECTURE_TTS` | `auto` (default), `gemini`, `elevenlabs`, or `edge` |
| `ELEVENLABS_API_KEY` | If set, `auto` usually prefers ElevenLabs |
| `GEMINI_TTS_MODEL` | Optional Gemini TTS model override |
| `EDGE_TTS_VOICE` | Optional Edge TTS voice (default `en-US-GuyNeural`) |

**TTS behavior:** `auto` prefers ElevenLabs when a key is set; otherwise tries **Gemini TTS** (may require a supported model/account) and falls back to **Microsoft Edge TTS** (no API key, network required).

## Run

From the repository root:

```bash
export GOOGLE_API_KEY=...   # or GEMINI_API_KEY
python run_lecture_pipeline.py
```

This will:

1. Build **`style.json`** from the transcript (if missing, or use `--force-style`).
2. Create **`projects/project_YYYYMMDD_HHMMSS/`** with rasterized PNGs, JSON artifacts, `audio/slide_XXX.mp3`, and **`Lecture_17_AI_screenplays.mp4`** (basename follows the PDF).

Useful flags:

- `--pdf` / `--transcript` — alternate inputs
- `--project-dir path` — reuse an existing project folder
- `--skip-tts` — stop after `slide_description_narration.json`
- `--skip-video` — generate MP3s only
- `--tts-engine edge` — force free Edge TTS
- `--force-narration`, `--force-slides`, etc. — regenerate specific stages

## Agents (in `lecture_agents/`)

| Module | Role |
|--------|------|
| `style_agent.py` | Transcript → `style.json` (tone, pacing, fillers, framing, narration guidance) |
| `pdf_rasterize.py` | PDF → `slide_images/slide_XXX.png` (PyMuPDF) |
| `slide_description_agent.py` | Each slide image + prior descriptions → `slide_description.json` |
| `premise_agent.py` | Slide descriptions → `premise.json` |
| `arc_agent.py` | Premise + descriptions → `arc.json` |
| `narration_agent.py` | Per slide: image + style + premise + arc + full descriptions + prior narrations → `slide_description_narration.json` (title slide: self-intro + topic summary) |
| `tts_step.py` | Narrations → `audio/slide_XXX.mp3` |
| `video_assembly.py` | ffmpeg: image + audio per slide (`-shortest`), then concat |

## Submission notes

- Submit the **GitHub repo URL** on Canvas.
- **Do not** commit PNG, MP3, or MP4 files; `.gitignore` excludes them under `projects/`.
- Include the **PDF** at the repo root so the grader can run the script without searching for the deck.
