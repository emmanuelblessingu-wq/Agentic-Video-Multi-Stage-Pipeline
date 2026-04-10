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
├── Lecture_17_transcript.txt       # captions/transcript for style (e.g. linked lecture section captions)
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

Place **`Lecture_17_AI_screenplays.pdf`** and a plain-text **caption/transcript file** (default `Lecture_17_transcript.txt`, or `--transcript`) in the repo root before running. The style step expects the instructor’s spoken text (e.g. exported captions for a lecture section).

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
| `GEMINI_AGENT_MODEL` | Optional; default `gemini-2.5-flash` (override if Google renames models) |
| `GEMINI_MAX_RETRIES` | Optional; default `12` — retries on HTTP 408/429/5xx (e.g. 503 overload) |
| `GEMINI_RETRY_BASE_SEC` | Optional; default `4` — base seconds for exponential backoff (capped at 120s) |
| `GEMINI_PAUSE_BETWEEN_SLIDES_SEC` | Optional; default `0` — e.g. `2` or `5` to **wait between slides** and reduce burst traffic (503s) |
| `LECTURE_TTS` | `auto` (default), `gemini`, `elevenlabs`, or `edge` |
| `ELEVENLABS_API_KEY` | If set, `auto` usually prefers ElevenLabs |
| `GEMINI_TTS_MODEL` | Optional Gemini TTS model override |
| `EDGE_TTS_VOICE` | Optional Edge TTS voice (default `en-US-GuyNeural`) |

**TTS behavior:** `auto` prefers ElevenLabs when a key is set; otherwise tries **Gemini TTS** (may require a supported model/account) and falls back to **Microsoft Edge TTS** (no API key, network required).

**Easing Gemini load (503 / “high demand”):** use a lighter model (`GEMINI_AGENT_MODEL=gemini-2.5-flash-lite` or `gemini-1.5-flash`), add **`GEMINI_PAUSE_BETWEEN_SLIDES_SEC=3`** between slides, raise **`GEMINI_MAX_RETRIES`**, and run at off-peak times. Paid Google AI / higher quotas can also help.

## Run

From the repository root:

```bash
export GOOGLE_API_KEY=...   # or GEMINI_API_KEY (optional if set in `.env`)
python run_lecture_pipeline.py
```

If you use a `.env` file in the repo root (`GOOGLE_API_KEY=...`), run `pip install -r requirements.txt` (includes `python-dotenv`); the entrypoint loads it automatically.

This will:

1. Build **`style.json`** from the transcript (if missing, or use `--force-style`).
2. Create **`projects/project_YYYYMMDD_HHMMSS/`** with rasterized PNGs, JSON artifacts, `audio/slide_XXX.mp3`, and **`Lecture_17_AI_screenplays.mp4`** (basename follows the PDF).

Useful flags:

- `--pdf` / `--transcript` — alternate inputs
- `--project-dir path` — reuse an existing project folder (required to **resume** after a crash or 503: slide descriptions and narrations are **checkpointed** to JSON after each slide)
- `--skip-tts` — stop after `slide_description_narration.json`
- `--skip-video` — generate MP3s only
- `--tts-engine edge` — force free Edge TTS
- `--force-narration`, `--force-slides`, etc. — regenerate specific stages

## Agents (in `lecture_agents/`)

| Module | Role |
|--------|------|
| `style_agent.py` | Transcript → `style.json` (tone, pacing, fillers, framing, narration guidance) |
| `pdf_rasterize.py` | PDF → `slide_images/slide_XXX.png` (PyMuPDF) |
| `slide_description_agent.py` | Each slide image + **all** prior slide descriptions in context → `slide_description.json` |
| `premise_agent.py` | Slide descriptions → `premise.json` |
| `arc_agent.py` | Premise + descriptions → `arc.json` |
| `narration_agent.py` | Per slide: image + style + premise + arc + full `slide_description.json` + **all** prior narrations (none on slide 1) → `slide_description_narration.json` (title slide: self-intro + topic overview) |
| `tts_step.py` | Reads narration strings from `slide_description_narration.json` → `audio/slide_XXX.mp3` (streaming providers merge chunks into one file per slide) |
| `video_assembly.py` | ffmpeg: image + audio per slide (`-shortest`), then concat |

## Grading rubric alignment (100 points)

| Points | Requirement | Implementation |
|--------|----------------|----------------|
| **8** | Style from instructor caption/transcript → `style.json` at repo root | `lecture_agents/style_agent.py`; input path `--transcript` (default `Lecture_17_transcript.txt`) |
| **18** | Slide agent: rasterized deck + current image + **all** previous descriptions in context each time → `slide_description.json` | `slide_description_agent.py` passes the full list of prior descriptions on every call (slides 1…N−1) |
| **10** | Premise: entire `slide_description.json` → `premise.json` | `premise_agent.py` loads the full JSON file into the prompt |
| **10** | Arc: `premise.json` + `slide_description.json` → coherent `arc.json` | `arc_agent.py` |
| **18** | Narration: current image + `style.json` + premise + arc + full slide descriptions + **all** prior narrations (none on slide 1) → `slide_description_narration.json`; title slide with self-intro + overview | `narration_agent.py` |
| **14** | Audio: narration strings → `audio/slide_NNN.mp3` (merge streamed chunks per slide) | `tts_step.py` (e.g. ElevenLabs iterator written to one file; Gemini/Edge single response or save) |
| **12** | Video: matching PNGs + MP3s → one `.mp4` named like PDF; segment length follows audio (`-shortest`) | `video_assembly.py` |
| **10** | Repo: code + project JSON + README; **no** committed images/audio/video | `.gitignore`; commit JSON under `projects/...` after a run if your course expects artifacts in the repo |

*Very long decks:* passing every prior description and narration grows prompts quickly; if the API hits context limits, use a larger-context Gemini model via `GEMINI_AGENT_MODEL` or split the assignment deck per course instructions.

## Submission notes

- Submit the **GitHub repo URL** on Canvas.
- **Do not** commit PNG, MP3, or MP4 files; `.gitignore` excludes them under `projects/`.
- Include the **PDF** at the repo root so the grader can run the script without searching for the deck.

Public repo: [emmanuelblessingu-wq/Agentic-Video-Multi-Stage-Pipeline](https://github.com/emmanuelblessingu-wq/Agentic-Video-Multi-Stage-Pipeline).
