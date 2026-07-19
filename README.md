# PawPal+ — Applied AI System (Project 4)

## Base Project

This project extends **PawPal+**, originally built for CodePath AI110 Module 2
(`ai110-module2show-pawpal-starter`). The original PawPal+ is a rule based pet
care scheduler. It lets an owner add pets and tasks (walks, feeding, meds,
grooming), then builds a daily plan by sorting tasks by time and priority,
fitting them into a time budget, and flagging scheduling conflicts. It has no AI
in it. Every decision is plain Python logic.

## Summary

PawPal+ Applied AI System keeps all of that scheduling logic and adds two new
things: live conflict detection, and an AI agent that can fix conflicts on its
own. When two tasks overlap, the user can fix it by hand (edit or delete a
task), or click "Resolve conflicts with AI." That button runs an agent that
looks up pet care tips, asks Gemini for a new time, applies the fix, and checks
that the conflict is actually gone. If the AI does not respond properly, the
agent falls back to a simple, safe rule instead.

## Architecture Overview

The full system flow is shown as a diagram in
[`diagrams/architecture.mmd`](diagrams/architecture.mmd). At a high level:

1. **UI (`app.py`)**: the user adds, edits, or deletes tasks. These become
   `Owner`, `Pet`, and `Task` objects.
2. **Scheduler (`pawpal_system.py`)**: filters tasks, sorts them, fits them into
   a time budget, and finds conflicts with `find_conflicts()`.
3. **Conflict branch**: if conflicts exist, the user can fix them by hand
   (edit/delete) or use the AI agent.
4. **AI Agent (`ai_agent.py`)**: for each conflict, it does four steps:
   - **Retrieve**: `find_relevant_tips()` finds helpful tips from
     `care_tips.md` by matching keywords.
   - **Plan and act**: it builds a prompt and calls Gemini (`gemini-3.5-flash`)
     through `call_gemini_model()`, asking for a new start time that does not
     overlap.
   - **Fallback**: if the API call fails, or the reply is not a valid time
     like `HH:MM`, the agent uses a simple backup rule instead (end time plus
     15 minutes). This is marked `source: fallback`, so it is never confused
     with a real AI answer.
   - **Check**: the agent runs `find_conflicts()` again to see if the fix
     worked. If not, it tries again, up to a set number of attempts, before
     giving up and reporting that conflict as unresolved.
5. **Tests (`tests/`)**: `test_pawpal.py` (27 tests) checks the scheduler logic.
   `test_ai_agent.py` (6 tests) checks the agent using fake AI replies, so the
   tests run without needing internet or real API calls.

The class level design (attributes and methods) is in
[`diagrams/uml_final.mmd`](diagrams/uml_final.mmd) from the original Module 2
project.

## Setup Instructions

```bash
# Clone the repo
git clone https://github.com/zuhaib1906/pawpal-plus-applied-ai-system.git
cd pawpal-plus-applied-ai-system

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set up your Gemini API key
cp .env.example .env
# then edit .env and add your real key:
# GEMINI_API_KEY=your-key-here
```

You can get a free Gemini API key at
[aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey).

**Run the tests:**
```bash
pytest
```

**Run the simple CLI demo:**
```bash
python3 main.py
```

**Run the full app:**
```bash
streamlit run app.py
```

## Sample Interactions

### 1. Core scheduling logic (`python3 main.py`)

```
All tasks sorted by time (sort_by_time)
----------------------------------------
  07:30 — Feed Cat (Rimuru)
  08:00 — Morning Walk (Filo)
  08:00 — Give Meds (Filo)
  09:00 — Feed Dog (Filo)
  12:00 — Clean Litter (Rimuru)
  18:00 — Evening Walk (Filo) [done]

Filo's tasks only (filter_tasks by pet)
----------------------------------------
  08:00 — Morning Walk
  08:00 — Give Meds
  09:00 — Feed Dog
  18:00 — Evening Walk

Pending tasks only (filter_tasks by status)
----------------------------------------
  07:30 — Feed Cat (Rimuru)
  08:00 — Morning Walk (Filo)
  08:00 — Give Meds (Filo)
  09:00 — Feed Dog (Filo)
  12:00 — Clean Litter (Rimuru)

Full daily plan (generate_schedule)
----------------------------------------
Daily plan for Zuhaib DADA — Monday
  07:30 — Feed Cat (Rimuru, 5 min) [priority: medium]
  08:00 — Morning Walk (Filo, 30 min) [priority: high]
  08:00 — Give Meds (Filo, 5 min) [priority: high]
  09:00 — Feed Dog (Filo, 10 min) [priority: medium]
  12:00 — Clean Litter (Rimuru, 10 min) [priority: low]
Scheduled 5 task(s) for Monday, ordered by start time then priority (untimed
tasks placed last). Time conflicts detected: Morning Walk and Give Meds both at
08:00 (same pet).

Conflict check (conflict_warning)
----------------------------------------
⚠️ 1 time conflict: Morning Walk & Give Meds (both at 08:00, same pet)
```

### 2. AI agent fixing a real conflict (Streamlit app)

Input: two overlapping tasks for different pets.

```
08:00 — Morning walk (Mochi, 20 min, High)
08:20 — Morning walk (Rimuru, 26 min, High)   ← overlaps Mochi's walk
```

Clicking "Resolve conflicts with AI":

```
🤖 AI conflict resolution
moved Morning walk to 08:20 — AI decision; resolved ✅
```

The prompt sent to Gemini includes the conflicting tasks' names, pet names,
start times, durations, and any related tips found in `care_tips.md`. Gemini
gave back a valid new start time, which was applied and checked to confirm the
conflict was gone.

### 3. Clean schedule with no conflicts (Streamlit app)

Input: four tasks that do not overlap, across two pets.

```
08:00 — Morning walk (Mochi, 20 min, High)
08:20 — Morning walk (Rimuru, 26 min, High)
09:00 — Meds (Rimuru, 5 min, High)
09:10 — Play time (Mochi, 15 min, High)
```

Clicking "Generate schedule":

```
📅 Daily plan for Jordan — Monday
Scheduled tasks: 4
Planned time: 66 min

08:00 — Morning walk — Mochi — 20 min — High
08:20 — Morning walk — Rimuru — 26 min — High
09:00 — Meds — Rimuru — 5 min — High
09:10 — Play time — Mochi — 15 min — High

No time conflicts. ✅
Scheduled 4 task(s) for Monday, ordered by start time then priority (untimed
tasks placed last).
```

## Design Decisions and Trade-offs

- **Warn, but do not block, when a conflict is created.** If a user adds or
  edits a task that overlaps another one, the app shows a warning but still
  saves the task. In real life, a pet owner sometimes needs two things to
  happen at the same time. Blocking that outright felt too strict.

- **Keyword matching instead of embeddings for retrieval.** `find_relevant_tips()`
  matches keywords between task names and lines in `care_tips.md`. With only
  about 8 short tips, a full embedding search would add complexity without
  really making the results better.

- **A safe fallback, always.** If Gemini fails, or its answer is not a valid
  time, the agent uses a fixed backup rule (end time plus 15 minutes) instead
  of leaving the conflict unresolved. Every result is marked `source: "ai"` or
  `source: "fallback"`, so it is always clear which one made the decision. This
  mattered a lot after we found, during testing, that a missing package was
  silently making every single fix use the fallback path (more on this below).

- **A retry limit (`max_attempts=2`) for each conflict.** The agent checks its
  own work and tries again if a fix does not work, but it stops after a set
  number of tries so it cannot get stuck trying forever. If it cannot fix a
  conflict, it reports that clearly instead of looping.

- **Task IDs instead of matching by name.** At first, editing and deleting
  tasks matched by `task_name`. This broke once a recurring task could create
  a second task with the same name. Now every `Task` gets its own unique
  `task_id` (a UUID), so edits and deletes are never ambiguous, even when two
  tasks share a name.

## Testing Summary

**Automated tests: 33 out of 33 passing.** 27 tests check the core scheduler,
and 6 tests check the AI agent loop. All tests run offline, since the agent
tests use a fake AI reply instead of a real API call.

```
...................................                                    [100%]
33 passed in 0.03s
```

**What worked well:**
- The core scheduling logic (sorting, recurring tasks, time budgets, conflict
  detection) has stayed reliable since Module 2 and did not need any changes.
- The fallback rule keeps the app working even when the AI call fails, so the
  feature never leaves the user stuck.
- The retry and give up logic was tested with a fake AI that always proposes
  overlapping times. It correctly gives up after 2 tries instead of looping
  forever.

**What did not work at first, and what we learned:**
- During live testing, every single fix showed `source: "fallback"`, even
  though the code that called Gemini looked correct. After some digging, we
  found two separate problems. First, the new packages
  (`google-generativeai` and `python-dotenv`) were listed in
  `requirements.txt` but were never actually installed in the virtual
  environment that was running the app. This made the import fail quietly,
  and the failure was caught by the fallback's error handling, so it never
  showed up as an error. Second, once that was fixed, the model name we were
  using (`gemini-1.5-flash`) turned out to be retired and gave a 404 error.
  Switching to `gemini-3.5-flash` fixed it. The lesson here: a good fallback
  can hide a real bug if you do not also check that the main path is actually
  being used.
- A smaller near miss: an early version of `.env.example` briefly had a real
  API key in it instead of a placeholder. It was caught before it was
  committed, and the key was replaced right away just to be safe.

**Confidence: 4.5 out of 5 stars.** The scheduler logic is fully trusted. The
AI agent works well end to end, but like any feature that depends on an LLM,
its answers can vary a little from call to call, which is exactly why the
fallback rule exists as a safety net.

### Reliability Evaluation (Human-Verified Scenarios)

In addition to the 33 automated tests, the table below records manual test
runs against the live app, so the results can be read without watching a demo.

| Test Input | Evaluation Criteria | Result |
|---|---|---|
| 2 tasks, same pet, overlapping times, valid Gemini response | Agent proposes a non-overlapping time and marks `source: "ai"` | Pass |
| Gemini call fails (missing dependency, pre-fix) | Agent falls back to the +15 min rule instead of crashing, marks `source: "fallback"` | Pass |
| Gemini returns text that is not a valid `HH:MM` time (unit test, mocked) | Agent rejects the response and uses the fallback rule | Pass |
| Fake model that always proposes an overlapping time (unit test, mocked) | Agent retries up to `max_attempts`, then gives up and reports `resolved: False` instead of looping forever | Pass |
| 7 tasks, all overlapping at once (18 simultaneous conflicts) | App does not crash; badge and conflict list render correctly; agent resolves most conflicts | Pass |
| A completed task overlapping a pending task | Not counted as a conflict, since the completed task already happened | Pass |
| Task with an unparseable start time, e.g. `"not-a-time"` (unit test) | Sorts to the end of the list instead of crashing | Pass |
| Two tasks not involved in any conflict, agent runs on an unrelated conflict elsewhere | Untouched tasks are not modified by the agent (unit test, fake model raises if ever called on them) | Pass |

All 8 scenarios above passed. The one real failure found during development
(every resolution silently using the fallback rule instead of a real AI call)
was caught through this same kind of manual verification, not by the
automated test suite, since the automated tests use a mocked model and would
not have revealed a real integration bug. That is recorded in the "What did
not work at first" notes above.

## Reflection

This project taught me that adding AI to a working system is not just about
calling an API. Most of the real work was in the parts around the call: what
happens when it fails, how to know if its answer is trustworthy, and how to
test that logic without needing a live connection every time. The clearest
lesson came from a real bug during testing, where every AI resolution was
quietly using the fallback rule instead of a real answer. It took real
debugging to trace it back to two small issues (a missing package and a
retired model name), and it showed me that "it didn't crash" is not the same
as "it's working correctly."

For the graded responsible-AI reflection, including specific examples of
helpful and flawed AI suggestions during development, see
[`model_card.md`](model_card.md).