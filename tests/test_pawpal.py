"""Simple pytest tests for PawPal+."""

import os
import sys

# Make the project root importable when running pytest from anywhere.
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest

from pawpal_system import Owner, Pet, Task, Scheduler


def test_task_completion():
    """A task starts incomplete and becomes complete after mark_complete()."""
    task = Task("Morning walk", "Biscuit", duration=30, priority="high")

    assert task.completed is False

    task.mark_complete()

    assert task.completed is True


def test_task_addition():
    """Adding a task to a pet increases its task count by one."""
    pet = Pet("Biscuit", "Sam")

    initial_count = len(pet.tasks)

    pet.add_task(Task("Feeding", "Biscuit", duration=10, priority="high"))

    assert len(pet.tasks) == initial_count + 1


def _scheduler() -> Scheduler:
    """Build a Scheduler backed by an empty owner for unit tests."""
    return Scheduler(Owner("Tester"))


# ---------------------------------------------------------------------------
# Sorting Correctness
# ---------------------------------------------------------------------------

def test_sorting_orders_by_start_time():
    """Tasks come back in ascending start-time order regardless of input order."""
    tasks = [
        Task("Evening", "Filo", 30, "high", "18:00"),
        Task("Morning", "Filo", 30, "high", "08:00"),
        Task("Noon", "Filo", 10, "medium", "12:00"),
    ]

    ordered = _scheduler().sort_by_time(tasks)

    assert [t.task_name for t in ordered] == ["Morning", "Noon", "Evening"]


def test_sorting_untimed_tasks_go_last():
    """A task with no start_time sorts after every timed task."""
    tasks = [
        Task("Untimed", "Filo", 10, "high", None),
        Task("Late", "Filo", 10, "low", "23:59"),
        Task("Early", "Filo", 10, "low", "06:00"),
    ]

    ordered = _scheduler().sort_by_time(tasks)

    assert [t.task_name for t in ordered] == ["Early", "Late", "Untimed"]


def test_sorting_same_time_breaks_tie_by_priority():
    """When start times match, higher priority is ordered first."""
    tasks = [
        Task("Low", "Filo", 10, "low", "08:00"),
        Task("High", "Filo", 10, "high", "08:00"),
        Task("Medium", "Filo", 10, "medium", "08:00"),
    ]

    ordered = _scheduler().sort_by_time(tasks)

    assert [t.task_name for t in ordered] == ["High", "Medium", "Low"]


def test_sorting_malformed_time_does_not_crash():
    """Malformed time strings degrade gracefully instead of raising."""
    tasks = [
        Task("Good", "Filo", 10, "high", "08:00"),
        Task("Bad", "Filo", 10, "high", "not-a-time"),
    ]

    ordered = _scheduler().sort_by_time(tasks)

    # The unparseable time is treated as untimed and sorts last.
    assert [t.task_name for t in ordered] == ["Good", "Bad"]


def test_sorting_empty_list():
    """Sorting an empty list returns an empty list."""
    assert _scheduler().sort_by_time([]) == []


# ---------------------------------------------------------------------------
# Recurrence Logic
# ---------------------------------------------------------------------------

def test_recurrence_once_has_no_next_occurrence():
    """A one-off task never produces a follow-up occurrence."""
    task = Task("Vet visit", "Filo", 60, "high", "10:00", recurrence="once")

    assert task.next_occurrence() is None


def test_recurrence_weekly_repeats_on_same_day():
    """A weekly task's next occurrence keeps its anchored day and starts incomplete."""
    task = Task(
        "Bath", "Filo", 30, "medium", "09:00",
        recurrence="weekly", day="Monday",
    )
    task.mark_complete()

    nxt = task.next_occurrence()

    assert nxt is not None
    assert nxt.day == "Monday"
    assert nxt.start_time == "09:00"
    assert nxt.completed is False


def test_recurrence_daily_occurs_on_any_day():
    """A daily task runs on every weekday."""
    task = Task("Feed", "Filo", 5, "high", "07:00", recurrence="daily", day="Monday")

    assert task.occurs_on("Monday") is True
    assert task.occurs_on("Saturday") is True


def test_recurrence_weekly_occurs_only_on_its_day():
    """A weekly task runs only on its anchored day (case-insensitively)."""
    task = Task("Bath", "Filo", 30, "low", "09:00", recurrence="weekly", day="Monday")

    assert task.occurs_on("monday") is True
    assert task.occurs_on("Tuesday") is False


def test_recurrence_complete_task_attaches_next_to_same_pet():
    """Completing a recurring task adds its next occurrence to the owning pet."""
    owner = Owner("Tester")
    pet = Pet("Filo", "Tester")
    owner.add_pet(pet)
    task = Task("Walk", "Filo", 20, "high", "08:00", recurrence="weekly", day="Monday")
    pet.add_task(task)

    scheduler = Scheduler(owner)
    created = scheduler.complete_task(task)

    assert task.completed is True
    assert created in pet.tasks
    assert len(pet.tasks) == 2


# ---------------------------------------------------------------------------
# Conflict Detection
# ---------------------------------------------------------------------------

def test_conflict_same_start_time_is_flagged():
    """Two tasks at the same start time are reported as a same-time conflict."""
    tasks = [
        Task("Walk", "Filo", 30, "high", "08:00"),
        Task("Meds", "Filo", 5, "high", "08:00"),
    ]

    conflicts = _scheduler().find_conflicts(tasks)

    assert len(conflicts) == 1
    assert conflicts[0]["same_time"] is True
    assert conflicts[0]["same_pet"] is True


def test_conflict_partial_overlap_is_flagged():
    """A task starting before another ends counts as a conflict."""
    tasks = [
        Task("Walk", "Filo", 30, "high", "08:00"),   # 08:00–08:30
        Task("Groom", "Filo", 20, "low", "08:15"),   # starts inside the walk
    ]

    conflicts = _scheduler().find_conflicts(tasks)

    assert len(conflicts) == 1
    assert conflicts[0]["same_time"] is False


def test_conflict_adjacent_tasks_do_not_conflict():
    """A task starting exactly when another ends is not a conflict."""
    tasks = [
        Task("Walk", "Filo", 30, "high", "08:00"),   # 08:00–08:30
        Task("Feed", "Filo", 10, "medium", "08:30"),  # starts at the boundary
    ]

    assert _scheduler().find_conflicts(tasks) == []


def test_conflict_untimed_tasks_never_conflict():
    """Untimed tasks are excluded from conflict detection."""
    tasks = [
        Task("Untimed A", "Filo", 30, "high", None),
        Task("Untimed B", "Filo", 30, "high", None),
    ]

    assert _scheduler().find_conflicts(tasks) == []


def test_conflict_different_pets_flagged_as_different():
    """An overlap across pets is marked same_pet=False."""
    tasks = [
        Task("Walk", "Filo", 30, "high", "08:00"),
        Task("Feed", "Rimuru", 5, "medium", "08:00"),
    ]

    conflicts = _scheduler().find_conflicts(tasks)

    assert len(conflicts) == 1
    assert conflicts[0]["same_pet"] is False


# ---------------------------------------------------------------------------
# Task Identity
# ---------------------------------------------------------------------------

def test_every_task_gets_a_unique_id():
    """Two tasks with the same name still get distinct ids."""
    a = Task("Walk", "Filo", 20, "high", "08:00")
    b = Task("Walk", "Filo", 20, "high", "08:00")

    assert a.task_id != b.task_id


def test_next_occurrence_has_fresh_id():
    """A recurring task's next occurrence does not reuse the original's id."""
    task = Task("Walk", "Filo", 20, "high", "08:00", recurrence="weekly", day="Monday")

    nxt = task.next_occurrence()

    assert nxt is not None
    assert nxt.task_id != task.task_id


def test_edit_task_affects_only_the_matching_id():
    """Editing one task in a same-name pair leaves the other untouched."""
    pet = Pet("Filo", "Sam")
    done = Task("Walk", "Filo", 20, "high", "08:00", completed=True)
    pending = Task("Walk", "Filo", 20, "high", "18:00")
    pet.add_task(done)
    pet.add_task(pending)

    pet.edit_task(pending.task_id, priority="low")

    assert pending.priority == "low"
    assert done.priority == "high"  # the same-named sibling is unchanged


def test_delete_task_removes_only_the_matching_id():
    """Deleting one task in a same-name pair keeps the other."""
    pet = Pet("Filo", "Sam")
    done = Task("Walk", "Filo", 20, "high", "08:00", completed=True)
    pending = Task("Walk", "Filo", 20, "high", "18:00")
    pet.add_task(done)
    pet.add_task(pending)

    pet.delete_task(done.task_id)

    assert pet.tasks == [pending]


# ---------------------------------------------------------------------------
# Input Validation
# ---------------------------------------------------------------------------

def test_invalid_priority_is_rejected():
    """Creating a task with an unknown priority raises instead of defaulting."""
    with pytest.raises(ValueError):
        Task("Walk", "Filo", 20, "urgent", "08:00")


def test_non_positive_duration_is_rejected():
    """Zero or negative durations are rejected at creation."""
    with pytest.raises(ValueError):
        Task("Walk", "Filo", 0, "high", "08:00")
    with pytest.raises(ValueError):
        Task("Walk", "Filo", -5, "high", "08:00")


def test_edit_task_rejects_invalid_values():
    """Editing a task to an invalid priority or duration raises."""
    pet = Pet("Filo", "Sam")
    task = Task("Walk", "Filo", 20, "high", "08:00")
    pet.add_task(task)

    with pytest.raises(ValueError):
        pet.edit_task(task.task_id, priority="whenever")
    with pytest.raises(ValueError):
        pet.edit_task(task.task_id, duration=0)


def test_set_duration_and_priority_validates():
    """set_duration_and_priority rejects invalid input."""
    task = Task("Walk", "Filo", 20, "high", "08:00")

    with pytest.raises(ValueError):
        task.set_duration_and_priority(-1, "high")
    with pytest.raises(ValueError):
        task.set_duration_and_priority(10, "nope")


def test_failed_edit_leaves_task_untouched():
    """A rejected edit_task() applies none of its changes (atomic validation)."""
    task = Task("Walk", "Filo", 20, "high", "08:00")

    # A valid duration paired with an invalid priority in the same call.
    with pytest.raises(ValueError):
        task.edit_task(duration=45, priority="urgent")

    # The whole call failed, so the original values must survive.
    assert task.duration == 20
    assert task.priority == "high"


def test_failed_set_duration_and_priority_leaves_task_untouched():
    """A rejected set_duration_and_priority() changes neither field."""
    task = Task("Walk", "Filo", 20, "high", "08:00")

    with pytest.raises(ValueError):
        task.set_duration_and_priority(45, "urgent")

    assert task.duration == 20
    assert task.priority == "high"
