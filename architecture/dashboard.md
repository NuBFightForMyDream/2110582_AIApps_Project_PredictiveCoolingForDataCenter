# Dashboard

[Architecture index](README.md)

A multipage Streamlit app (`app.py` + `app_pages/` + `ui/`) with a top menu:

| Menu | Pages |
|---|---|
| — | Overview · Ask the agents |
| Operations | Live plant · Equipment health · Upgrade advisor · Security |
| How the AI decides | 1 Sensors · 2 Clean data · 3 Forecast · 4 Plan (MPC) · 5 Safety · 6 Results |

- **One moment for the whole app**: the sidebar picks a 15-minute moment in the test weeks, with *Jump to* shortcuts
  (`ui/common.py: moment_picker`). Every moment-based page follows it.
- **Same page shape**: `page_header()` gives the title, the question the page answers, three plain-language points and a small
  SVG illustration (`ui/art.py`, in the cover's style); diagrams and method notes sit in collapsed *How it works* expanders.
- **Native elements only**: no custom CSS; Material icons, bordered metrics, badges, Plotly charts, Mermaid diagrams.
- **Nothing is cut off**: metric cards go through `kpi_row()` (`ui/common.py`): each gets a fixed width computed from its
  label, value and note, inside a horizontal container that wraps onto the next row when the page narrows (e.g. the
  sidebar opens). Long text (an answer, an option's name) goes in a wrapping text card, not a metric. A test checks
  every metric on every page.
- **Performance**: the study loads once per process (`st.cache_resource`); each page computes only itself (< 0.3 s); the
  agent case runs in a fragment so *Run case* does not rerun the page.
- Tests: `tests/test_app.py` renders all 12 pages headless (Streamlit `AppTest`) and checks that pages follow the sidebar.
