# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Environment
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Run the Streamlit UI (opens http://localhost:8501)
python3 -m streamlit run app.py

# Run the CLI demo (prints sorting/filtering/schedule/conflict output)
python3 main.py

# Tests
pytest                                   # full suite
pytest tests/test_pawpal.py -q           # one file
pytest tests/test_pawpal.py::test_sorting_untimed_tasks_go_last   # single test
pytest --cov                             # with coverage
```

Note: use `python3`; `python` is not on PATH in this environment.

## Architecture

All domain logic lives in a single module, [pawpal_system.py](pawpal_system.py), with a strict layering:

- **`Task`, `Pet`, `Owner`** are `@dataclass`es holding data and simple self-mutations. Ownership is nested: `Owner.pets` → `Pet.tasks`. `Owner.all_tasks()` flattens this into one list, which is the input to almost every `Scheduler` method.
- **`Scheduler`** is the only class with real algorithms. It holds a reference to one `Owner` and is otherwise stateless except for `self.reasoning`, a human-readable string rebuilt on each `generate_schedule` call.

Both entry points ([app.py](app.py) Streamlit UI, [main.py](main.py) CLI demo) are thin: they construct `Owner`/`Pet`/`Task` objects and call `Scheduler` methods. Keep scheduling logic out of these files — they exist to display results, not compute them.

### Scheduler conventions that matter

- **Time is normalized through `_to_minutes`**, which maps `None`/malformed times to a large sentinel (`_NO_TIME`) so untimed tasks always sort last instead of raising. Any new time-based logic should route through this helper rather than parsing `HH:MM` directly.
- **Sorting** (`sort_by_time`) uses the composite key `(start_minute, priority_rank)` — a stable sort, so equal keys preserve insertion order. Priority ordering comes from the `_PRIORITY` dict (`high=0, medium=1, low=2`; lower = more important).
- **`generate_schedule`** is the orchestrator: filter by pet/status → drop tasks not due that day (`Task.occurs_on`) → greedily trim to `Owner.available_minutes` if a budget is set (0 means unlimited) → re-sort by time → detect conflicts → build `reasoning`. It sorts by *priority* to choose what fits, then re-sorts by *time* for display; don't collapse these two passes.
- **Conflict detection** (`find_conflicts`) compares each task's `[start, end)` span against following tasks and breaks early once no overlap is possible. Adjacent tasks (one ends exactly when the next starts) do **not** conflict. `conflict_warning` wraps it defensively and never raises.
- **Recurrence**: `Task.occurs_on(day)` decides visibility for a given weekday; `Task.next_occurrence()` builds the follow-up instance; `Scheduler.complete_task` marks done and attaches the next occurrence to the *same pet* (matched by object identity, not name).

### Testing notes

- Tests live in [tests/test_pawpal.py](tests/test_pawpal.py), grouped by comment headers (Sorting Correctness / Recurrence Logic / Conflict Detection).
- `Task.next_occurrence()` for `daily` recurrence calls `datetime.date.today()`, making it date-dependent — tests deliberately avoid asserting the exact rolled-over day. Prefer `weekly` recurrence (deterministic) in tests, or inject the date if you extend this.

## Project docs

[reflection.md](reflection.md) records design decisions and rationale; [diagrams/](diagrams/) holds the UML (`uml.mmd` original, `uml_final.mmd` matching current code). The README's "Smarter Scheduling" table maps user-facing features to their backing methods — keep it in sync when adding scheduler capabilities.
