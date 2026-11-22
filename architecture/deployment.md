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
| Tests | `.venv/bin/python -m pytest -q` (118 tests, ≈ 2 min) |
| README figures | `pip install -r requirements-dev.txt`, then `python scripts/make_figures.py` |

`tests/test_storage.py` checks that the SQL check constraints accept every task and agent mode the code can save.
