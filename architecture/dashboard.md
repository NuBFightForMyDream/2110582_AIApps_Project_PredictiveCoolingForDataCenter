# Dashboard

[Architecture index](README.md)

A multipage Streamlit app (`app.py` + `app_pages/` + `ui/`) with seven pages in a top menu:

| Page | Main view | Folded under "More detail" |
|---|---|---|
| Overview | cover, four headline numbers, the loop in one line, links | — |
| Ask the agents | task + *Run case*; the answer, status chips, the forecast | options (question, AI model, simulated problems), trace + G3 checks, security and hardware reports, signed answer and raw evidence, case history |
| Results | four headline numbers, scenario picker, energy and overheating bars, one zoom chart | average power, every scenario's numbers, baselines |
| Data center | five key numbers, the live plant drawing, findings that need action | energy and heat Sankeys, fault trends, every device and the gateway view, installed models |
| Security | attack picker, minutes above 27 °C with and without the check, the attack chart, the prompt screen | how the defences work, attack numbers, STRIDE and protocols |
| Upgrades | today's numbers, fastest payback and largest saving, savings chart | your own CAPEX, all numbers and the method |
| How it works | the loop and one step at a time (sensors, clean, forecast, plan, safety) | each step's secondary charts and tables, the what-if forecast |

- **One moment for the whole app**: the sidebar picks a 15-minute moment in the test weeks, with *Jump to* shortcuts
  (`ui/common.py: moment_picker`). Every moment-based page follows it.
- **Same page shape**: `page_header()` gives the title, one plain sentence and a small SVG illustration (`ui/art.py`, in
  the cover's style). Below it: at most one row of key numbers, one picker, one main chart. Everything else (diagrams,
  method notes, full tables, secondary charts) sits in collapsed *More detail* expanders (`how_it_works()`).
- **Few clicks**: a flat menu of seven pages; the five loop steps share one page with a step picker (`ui/steps.py`);
  the plant drawing, Sankeys and trends live in `ui/plant.py`.
- **Native elements only**: no custom CSS; Material icons, bordered metrics, badges, Plotly charts, Mermaid diagrams.
- **Nothing is cut off**: metric cards go through `kpi_row()` (`ui/common.py`): each gets a fixed width computed from its
  label, value and note, inside a horizontal container that wraps onto the next row when the page narrows (e.g. the
  sidebar opens). A test checks every metric on every page and step.
- **Performance**: the study loads once per process (`st.cache_resource`); each page computes only itself (< 0.3 s); the
  agent case runs in a fragment so *Run case* does not rerun the page.
- Tests: `tests/test_app.py` renders all 7 pages and the 5 steps headless (Streamlit `AppTest`), checks that pages
  follow the sidebar moment, and measures every metric card.
