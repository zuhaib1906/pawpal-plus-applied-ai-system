"""PawPal+ AI agent — resolves scheduling conflicts with an LLM + light RAG.

The agent follows a retrieve → plan/act → check/retry loop:

1. RETRIEVE relevant care tips for a conflict via keyword matching (find_relevant_tips).
2. PLAN/ACT by asking a model for a new start time (propose_resolution), with a
   deterministic fallback when the model's answer can't be parsed.
3. CHECK/RETRY by re-detecting conflicts after each move, retrying a stubborn
   conflict up to max_attempts before giving up (resolve_conflicts).

The real Gemini call lives in call_gemini_model() and is injected via the
`call_model` parameter, so tests can swap in a fake and run offline.
"""

import os
import re

from pawpal_system import Owner, Scheduler, Task

CARE_TIPS_PATH = os.path.join(os.path.dirname(__file__), "care_tips.md")

# Matches an HH:MM time (1-2 digit hour, 2 digit minute) anywhere in a string.
_HHMM_RE = re.compile(r"\b(\d{1,2}):([0-5]\d)\b")

# Minutes added after the first task's end when the model answer can't be used.
_FALLBACK_GAP_MINUTES = 15


# ---------------------------------------------------------------------------
# Small time helpers (kept local so the agent doesn't depend on Scheduler internals)
# ---------------------------------------------------------------------------

def _to_minutes(hhmm: str) -> int:
    """Convert an "HH:MM" string to minutes since midnight."""
    hours, minutes = hhmm.split(":")
    return int(hours) * 60 + int(minutes)


def _to_hhmm(total_minutes: int) -> str:
    """Convert minutes-since-midnight back to a zero-padded "HH:MM" (clamped to a day)."""
    total_minutes = max(0, min(total_minutes, 23 * 60 + 59))
    return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"


def _parse_hhmm(text: str) -> str | None:
    """Return a normalized "HH:MM" found in `text`, or None if there isn't one.

    Defensive: strips whitespace, searches for the first HH:MM token, and
    rejects hours past 23 so garbage responses fall through to the fallback.
    """
    if not isinstance(text, str):
        return None
    match = _HHMM_RE.search(text.strip())
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23:
        return None
    return f"{hour:02d}:{minute:02d}"


def load_care_tips() -> str:
    """Read care_tips.md, or return "" if it is missing."""
    try:
        with open(CARE_TIPS_PATH, encoding="utf-8") as handle:
            return handle.read()
    except FileNotFoundError:
        return ""


# ---------------------------------------------------------------------------
# a. RETRIEVE
# ---------------------------------------------------------------------------

def find_relevant_tips(conflict: dict, tips_text: str) -> str:
    """Return the 1-3 tips most relevant to a conflict, as plain text.

    Basic RAG: tokenize the two conflicting task names, then score each tip
    line by how many of those keywords it contains. Returns the top matches
    (highest overlap first), or "" when nothing overlaps.
    """
    first, second = conflict["first"], conflict["second"]
    keywords = set(re.findall(r"[a-z]{3,}", f"{first.task_name} {second.task_name}".lower()))

    scored = []
    for line in tips_text.splitlines():
        stripped = line.strip().lstrip("-").strip()
        # Skip blanks and the markdown heading.
        if not stripped or stripped.startswith("#"):
            continue
        line_words = set(re.findall(r"[a-z]{3,}", stripped.lower()))
        overlap = len(keywords & line_words)
        if overlap:
            scored.append((overlap, stripped))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return "\n".join(tip for _, tip in scored[:3])


# ---------------------------------------------------------------------------
# c. The isolated Gemini call (mocked in tests via the call_model parameter)
# ---------------------------------------------------------------------------

def call_gemini_model(prompt: str) -> str:
    """Send `prompt` to Gemini and return the raw text response.

    Imports google-generativeai and python-dotenv lazily so that importing this
    module (and running the tests) never requires them or a network connection.
    """
    from dotenv import load_dotenv

    load_dotenv()
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set (add it to your .env file).")

    import google.generativeai as genai

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-3.5-flash")
    response = model.generate_content(prompt)
    return response.text


# ---------------------------------------------------------------------------
# b. PLAN / ACT
# ---------------------------------------------------------------------------

def _build_prompt(conflict: dict, relevant_tips: str) -> str:
    """Build the model prompt describing the conflict and the retrieved tips."""
    first, second = conflict["first"], conflict["second"]
    end_time = _to_hhmm(_to_minutes(first.start_time) + first.duration)
    who = "the same pet" if conflict["same_pet"] else "different pets"
    return (
        "You are a pet-care scheduling assistant. Two care tasks overlap in time "
        "and you must reschedule the second one.\n"
        f"Task A: '{first.task_name}' for {first.pet_name}, "
        f"starts {first.start_time}, lasts {first.duration} minutes (ends {end_time}).\n"
        f"Task B: '{second.task_name}' for {second.pet_name}, "
        f"starts {second.start_time}, lasts {second.duration} minutes.\n"
        f"The two tasks involve {who}.\n\n"
        "Relevant pet-care tips:\n"
        f"{relevant_tips or '(no specific tips found)'}\n\n"
        f"Choose a new start time for Task B so it begins after Task A ends "
        f"({end_time}), respecting any gap the tips recommend.\n"
        "Respond with ONLY the new start time in 24-hour HH:MM format, nothing else."
    )


def propose_resolution(conflict: dict, relevant_tips: str, call_model) -> tuple[str, str]:
    """Ask the model for a new start time for the conflict's second task.

    Returns (new_start_time, source) where source is "ai" when the model gave a
    parseable HH:MM answer, or "fallback" when we fell back to the deterministic
    rule: first task's end time + 15 minutes.
    """
    first = conflict["first"]
    prompt = _build_prompt(conflict, relevant_tips)

    raw = ""
    try:
        raw = call_model(prompt)
    except Exception:
        # Any model/network error drops us straight to the fallback rule.
        raw = ""

    parsed = _parse_hhmm(raw)
    if parsed is not None:
        return parsed, "ai"

    fallback = _to_hhmm(_to_minutes(first.start_time) + first.duration + _FALLBACK_GAP_MINUTES)
    return fallback, "fallback"


# ---------------------------------------------------------------------------
# d. CHECK / RETRY (top-level loop)
# ---------------------------------------------------------------------------

def _pending_day_tasks(scheduler: Scheduler, owner: Owner, day: str) -> list[Task]:
    """Pending tasks that occur on the given day (the set conflicts are drawn from)."""
    pending = scheduler.filter_tasks(owner.all_tasks(), status="pending")
    return [task for task in pending if task.occurs_on(day)]


def _day_conflicts(scheduler: Scheduler, owner: Owner, day: str) -> list[dict]:
    """Current conflicts among pending tasks on the given day."""
    return scheduler.find_conflicts(_pending_day_tasks(scheduler, owner, day))


def _pair_still_conflicts(
    scheduler: Scheduler, owner: Owner, day: str, id_a: str, id_b: str
) -> bool:
    """Return whether the specific task pair still overlaps after a move."""
    for conflict in _day_conflicts(scheduler, owner, day):
        ids = {conflict["first"].task_id, conflict["second"].task_id}
        if ids == {id_a, id_b}:
            return True
    return False


def _owning_pet(owner: Owner, task_id: str):
    """Return the Pet that owns a given task id, or None."""
    for pet in owner.pets:
        if any(task.task_id == task_id for task in pet.tasks):
            return pet
    return None


def resolve_conflicts(
    owner: Owner, day: str, max_attempts: int = 2, call_model=call_gemini_model
) -> list[dict]:
    """Resolve pending-task conflicts for `day` by rescheduling the later task.

    For each conflict: retrieve tips, propose a new start time, apply it via
    Pet.edit_task(), and re-check. A conflict that survives is retried up to
    max_attempts before being reported as unresolved. Non-conflicting tasks are
    never touched.

    Returns a list of result dicts:
        {"conflict": <conflict dict>, "action": "moved X to HH:MM",
         "source": "ai" | "fallback", "resolved": bool}

    `call_model` defaults to the real Gemini call but can be swapped for a fake
    in tests.
    """
    scheduler = Scheduler(owner)
    tips_text = load_care_tips()
    results: list[dict] = []
    gave_up: set[frozenset] = set()

    # Safety bound so a pathological model that keeps recreating conflicts can
    # never loop forever, independent of the per-conflict retry limit.
    initial = len(_pending_day_tasks(scheduler, owner, day))
    safety_cap = max(10, max_attempts * initial * initial)
    iterations = 0

    while iterations < safety_cap:
        iterations += 1

        # Pick the first conflict we haven't already given up on.
        target = None
        for conflict in _day_conflicts(scheduler, owner, day):
            key = frozenset((conflict["first"].task_id, conflict["second"].task_id))
            if key not in gave_up:
                target = conflict
                break
        if target is None:
            break  # nothing left to resolve

        first, second = target["first"], target["second"]
        key = frozenset((first.task_id, second.task_id))
        pet = _owning_pet(owner, second.task_id)

        if pet is None:
            gave_up.add(key)
            results.append(
                {
                    "conflict": target,
                    "action": f"could not locate {second.task_name}",
                    "source": "fallback",
                    "resolved": False,
                }
            )
            continue

        resolved = False
        action = ""
        source = "fallback"
        for _ in range(max_attempts):
            relevant = find_relevant_tips(target, tips_text)
            new_time, source = propose_resolution(target, relevant, call_model)
            pet.edit_task(second.task_id, start_time=new_time)
            action = f"moved {second.task_name} to {new_time}"
            if not _pair_still_conflicts(scheduler, owner, day, first.task_id, second.task_id):
                resolved = True
                break

        if not resolved:
            gave_up.add(key)

        results.append(
            {"conflict": target, "action": action, "source": source, "resolved": resolved}
        )

    return results
