# Deployment

[Architecture index](README.md)

One Streamlit service: LangGraph, the forecaster and all checks run inside it. Optional services are switched on by secrets.

| Secret | Enables |
|---|---|
| `GEMINI_API_KEY`, `GEMINI_MODEL` | Gemini agent mode |
| `ANTHROPIC_API_KEY` | Claude Haiku agent mode |
| `SUPABASE_URL`, `SUPABASE_KEY` (server-side secret key) | case history; run `supabase/migrations/001…003*.sql` in order |
| `COMMAND_SIGNING_KEY` | signatures that survive restarts (else an ephemeral key) |

Template: `.streamlit/secrets.toml.example`. On Streamlit Community Cloud pick `app.py` as the main file and Python 3.12;
`artifacts/bundle.pkl` is committed so the app starts without retraining (it is rebuilt automatically if scikit-learn differs).

| Task | Command |
|---|---|
| Run the app | `.venv/bin/python -m predictive_cooling` |
| Ask the agents | `.venv/bin/python -m predictive_cooling.agents --at "2026-04-21 00:30" [--mode analyze\|upgrade] [--fault B5 B6] [--equipment-fault CRAH-1] [--attack spoofing]` |
| Rebuild data / study | `python -m predictive_cooling.dataset`, `python -m predictive_cooling.hardware`, `python -m predictive_cooling.pipeline` |
| Tests | `.venv/bin/python -m pytest -q` (122 tests, ≈ 2 min) |
| README figures | `pip install -r requirements-dev.txt`, then `python scripts/make_figures.py` |

`tests/test_storage.py` checks that the SQL check constraints accept every task and agent mode the code can save.

## Step by step

**Streamlit Community Cloud (free)**

1. Push this branch to GitHub (`artifacts/bundle.pkl` is committed so the app starts without retraining).
2. On [share.streamlit.io](https://share.streamlit.io) → *Create app* → pick the repo, branch `claude-new-version`, main file `app.py`.
   Under *Advanced settings* choose **Python 3.12**.
3. Paste your secrets (template: `.streamlit/secrets.toml.example`). Every key is optional:
   - `GEMINI_API_KEY` (from Google AI Studio) enables the *Gemini* agent mode; set `GEMINI_MODEL = "gemini-3.5-flash-lite"` on a free key.
   - `ANTHROPIC_API_KEY` enables the *Claude* agent mode (Claude Haiku 5.5, billed per token).
   - `SUPABASE_URL` + `SUPABASE_KEY` enable the case history.
   - `COMMAND_SIGNING_KEY` (e.g. `python -c "import secrets; print(secrets.token_hex(32))"`) signs recommendations with a key
     that survives restarts; without it the key is ephemeral.

**Supabase case history (optional)**

1. Create a Supabase project and run `supabase/migrations/001_agent_cases.sql`, then `002_allow_claude_agent_mode.sql` and
   `003_allow_upgrade_task_and_new_statuses.sql`, in its SQL editor (003 lets *Plan upgrades* cases be saved).
2. Put the project URL and the **server-side secret key** in the secrets. The key stays on the server (Streamlit code
   never runs in the browser); RLS is on and the public roles get no access to the table.
3. Every *Run case* on the *Ask the agents* page is saved; *Case history (Supabase)* at the bottom of that page shows the latest 20.
   If Supabase is down the case still runs and a toast says it was not saved.

For local runs, copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` (git-ignored) or export the same
names as environment variables.
