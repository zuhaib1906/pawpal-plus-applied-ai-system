"""Reliability tests for the PawPal+ AI agent.

Every test injects a FAKE call_model, so these run fully offline with no
google-generativeai dependency and no network access.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import ai_agent
from pawpal_system import Owner, Pet, Scheduler, Task


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _owner_with_conflict():
    """Owner + pet with two overlapping pending tasks on Monday.

    'Morning Walk' (high, 08:00, 30 min) sorts first; 'Give Meds' (medium,
    08:00, 10 min) is the later/second task the agent will reschedule.
    """
    owner = Owner("Tester")
    pet = Pet("Filo", "Tester")
    owner.add_pet(pet)
    pet.add_task(Task("Morning Walk", "Filo", 30, "high", "08:00", day="Monday"))
    pet.add_task(Task("Give Meds", "Filo", 10, "medium", "08:00", day="Monday"))
    return owner, pet


def _conflicts(owner, day="Monday"):
    """Current pending-task conflicts for a day (mirrors the agent's own view)."""
    scheduler = Scheduler(owner)
    pending = scheduler.filter_tasks(owner.all_tasks(), status="pending")
    on_day = [t for t in pending if t.occurs_on(day)]
    return scheduler.find_conflicts(on_day)


def _fixed(value):
    """A fake model that always returns the same string."""
    return lambda prompt: value


# ---------------------------------------------------------------------------
# 1. A valid model response resolves a real conflict.
# ---------------------------------------------------------------------------

def test_valid_response_resolves_conflict():
    owner, pet = _owner_with_conflict()
    assert len(_conflicts(owner)) == 1  # conflict exists before

    results = ai_agent.resolve_conflicts(owner, "Monday", call_model=_fixed("09:00"))

    assert _conflicts(owner) == []  # conflict gone after
    assert len(results) == 1
    assert results[0]["resolved"] is True
    assert results[0]["source"] == "ai"
    assert "09:00" in results[0]["action"]

    # The second task was the one moved; the first is untouched.
    meds = next(t for t in pet.tasks if t.task_name == "Give Meds")
    walk = next(t for t in pet.tasks if t.task_name == "Morning Walk")
    assert meds.start_time == "09:00"
    assert walk.start_time == "08:00"


# ---------------------------------------------------------------------------
# 2. Retrieval connects tips to the conflict, and copes with no match.
# ---------------------------------------------------------------------------

def test_find_relevant_tips_matches_keywords():
    owner, _ = _owner_with_conflict()
    conflict = _conflicts(owner)[0]
    tips = ai_agent.load_care_tips()

    relevant = ai_agent.find_relevant_tips(conflict, tips)

    assert relevant  # non-empty
    # "Morning Walk" / "Give Meds" should surface walk- or medication-related tips.
    assert any(word in relevant.lower() for word in ("walk", "medication", "meds"))


def test_find_relevant_tips_no_match_does_not_crash():
    owner = Owner("Tester")
    pet = Pet("Filo", "Tester")
    owner.add_pet(pet)
    # Task names with no care keywords at all.
    pet.add_task(Task("Zzz", "Filo", 30, "high", "08:00", day="Monday"))
    pet.add_task(Task("Qqq", "Filo", 10, "medium", "08:00", day="Monday"))
    conflict = _conflicts(owner)[0]

    result = ai_agent.find_relevant_tips(conflict, ai_agent.load_care_tips())
    assert isinstance(result, str)  # empty is fine, just must not raise

    # Empty tips text is also safe.
    assert ai_agent.find_relevant_tips(conflict, "") == ""


# ---------------------------------------------------------------------------
# 3. A malformed response triggers the deterministic fallback.
# ---------------------------------------------------------------------------

def test_malformed_response_uses_fallback():
    owner, pet = _owner_with_conflict()

    results = ai_agent.resolve_conflicts(owner, "Monday", call_model=_fixed("banana"))

    assert len(results) == 1
    assert results[0]["source"] == "fallback"
    assert results[0]["resolved"] is True
    # Fallback rule: first task ends 08:30, +15 min = 08:45.
    meds = next(t for t in pet.tasks if t.task_name == "Give Meds")
    assert meds.start_time == "08:45"
    assert "08:45" in results[0]["action"]


# ---------------------------------------------------------------------------
# 4. A model that never resolves the conflict gives up (no infinite loop).
# ---------------------------------------------------------------------------

def test_gives_up_after_max_attempts():
    owner, _ = _owner_with_conflict()

    # Always proposes 08:00 — same as the first task, so the overlap persists.
    results = ai_agent.resolve_conflicts(
        owner, "Monday", max_attempts=2, call_model=_fixed("08:00")
    )

    assert len(results) == 1
    assert results[0]["resolved"] is False
    assert _conflicts(owner)  # conflict still present, agent didn't hang


# ---------------------------------------------------------------------------
# 5. Non-conflicting tasks are left completely untouched.
# ---------------------------------------------------------------------------

def test_non_conflicting_tasks_untouched():
    owner = Owner("Tester")
    pet = Pet("Filo", "Tester")
    owner.add_pet(pet)
    pet.add_task(Task("Morning Walk", "Filo", 30, "high", "08:00", day="Monday"))
    pet.add_task(Task("Feed Dog", "Filo", 10, "medium", "10:00", day="Monday"))

    # A fake that would move things if ever called.
    def boom(prompt):
        raise AssertionError("call_model should not be invoked when there are no conflicts")

    results = ai_agent.resolve_conflicts(owner, "Monday", call_model=boom)

    assert results == []
    assert [t.start_time for t in pet.tasks] == ["08:00", "10:00"]
