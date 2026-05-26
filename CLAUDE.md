# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Korean-language, 5-day hands-on training course ("삼성디스플레이 재직자 대상 AI Agent Architecture") that teaches AI agent construction through a fictional manufacturing scenario ("DisplayEdu Fab"). **All data, equipment IDs, alarm codes, and processes are intentionally fake** — the course is structured so learners can run everything with no API key. Source comments, prompts, and reports are in Korean; keep new strings consistent with the surrounding Korean style.

The five days build on each other:
- **day1** — Prompt / Chain / mini LangGraph / "Agent v0"
- **day2** — Markdown RAG, Chroma vector DB, LangGraph RAG agent
- **day3** — PostgreSQL manufacturing DB & log tools, RAG tool wrapper, FastMCP tool server/client, multi-agent roles
- **day4** — trace analysis, rule-based vs. LLM-based tool selection, tool-plan/contract validation, guardrails, quality gate
- **day5** — final FastMCP multi-agent, trace reviewer, edge-case runner, action lab

> Note: the working tree currently contains only `src/day1` and `src/llm`. `src/day2`–`src/day5` are tracked in git history (and described above) but are deleted/staged-out in the working tree. Restore them from git (`git show HEAD:<path>`) if you need to work on later days.

## Setup & common commands

A `.venv` already exists. On Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env   # default LLM_PROVIDER=mock works with no API key
```

**Always run from the project root** — scripts resolve paths via `Path(__file__).parents[2]` and manipulate `sys.path` assuming the root is the cwd.

```powershell
# CLI exercise (every module has a __main__ block)
python src/day1/simple_chain_starter.py

# Streamlit version (each exercise is paired with a *_streamlit_app.py)
streamlit run src/day1/day1_agent_v0_streamlit_app.py

# Exercise a module's self-test directly
python src/llm_client.py
python src/llm/mock_llm.py

# day3 PostgreSQL (uses POSTGRES_* vars from .env)
docker compose -f db/docker-compose.yml up -d
```

There is **no test framework, linter, or build step** configured. Modules are "tested" by running their `__main__` self-tests. Do not add a build/test toolchain unless asked. Note: `requirements.txt` is treated as fixed — several modules explicitly say not to modify it.

## Architecture

### LLM access goes through one seam: `src/llm_client.py`

This is the most important convention. **No agent/exercise code imports an LLM SDK directly** (no `openai`, `anthropic`, `google.genai`, `requests`-to-Ollama in feature files). Everything calls:

- `generate_response(prompt, allow_fallback=None, require_real_llm=False)` → `str`
- `generate_json_response(prompt, ...)` → `dict` (tolerant JSON extraction from markdown/prose; never raises — returns a dict with an `llm_error_code` on failure so callers like the day4 tool selector can fall back to rules)

`llm_client.py` reads `.env`, picks a provider from `LLM_PROVIDER` (`mock` | `local` | `cloud`), and delegates to:
- `src/llm/mock_llm.py` — offline canned Markdown keyed off alarm codes in the prompt (the default; no API key)
- `src/llm/local_llm.py` — Ollama via HTTP
- `src/llm/cloud_llm.py` — dispatches on `CLOUD_LLM_PROVIDER` to Gemini / OpenAI / Anthropic / NVIDIA (NVIDIA uses the OpenAI-compatible endpoint)

On a local/cloud call failure, it **falls back to mock by default** so a class never stalls. Pass `allow_fallback=False` (or set `LLM_DISABLE_MOCK_FALLBACK`) when you must distinguish a real LLM success from a mock — e.g. day4/day5 tool-plan generation. The `mock_fallback` itself is single-sourced in `generate_response`; provider sub-modules raise rather than fall back.

### Templating: prompts and reports are Mustache files, not inline strings

Prompt construction and report rendering are separated into `templates/dayN/*.mustache`, rendered with `pystache` (day1/2) or `chevron` (day4+). The typical flow in an exercise is: read input data → render a `*_prompt.mustache` → `generate_response` → render a `*_result.mustache` / `*_trace.mustache` → write to `outputs/dayN/` (gitignored). When changing prompt or report wording, edit the `.mustache` template, not the Python.

### LangGraph pattern (day1 mini graph, day2 RAG)

State is a plain `dict`; nodes are inner functions that mutate state and append a structured `trace` entry; a conditional edge routes on a `next_action` field (e.g. "has required equipment_id + alarm_code → search logs, else → ask for more info"). The Streamlit variants deliberately stop the graph at the prompt-build node so the learner can hand-edit the prompt before the LLM call.

### CLI + Streamlit pairing

Most exercises ship as a `_runner.py`/`_template.py`/`_starter.py` CLI plus a `*_streamlit_app.py` that mirrors the same logic in the browser. Keep the two in sync when editing shared behavior.

## Hard constraints baked into this codebase

These are enforced throughout and reviewers/tests assume them — follow them in any new code:

- **Never print or persist secrets**: no API keys, Bearer tokens, passwords, or full `os.environ` dumps in output, logs, traces, or Streamlit UI. `llm_client.py` masks secret-looking strings in error messages; reuse that approach rather than echoing raw exceptions.
- **Fictional data only**: never introduce real Samsung Display systems, equipment, recipes, or quality standards. Use the existing `EDU-LINE-*`, `EQP-*`, `ALM-*` style identifiers.
- **File I/O uses `encoding="utf-8-sig"`** everywhere (inputs are often saved from Windows Notepad with a BOM). Match this when reading/writing data, templates, or outputs.

## Path/import gotcha across days

`sys.path` handling differs by day, so imports look different:
- **day1** inserts `<root>/src` and imports top-level modules: `from llm_client import generate_response`, `from llm.mock_llm import ...`
- **day3+** insert `<root>` and import package-qualified: `from src.day3.postgres_db_tool import ...`

When adding a file, copy the `sys.path` setup from a sibling in the same day rather than assuming a single convention.
