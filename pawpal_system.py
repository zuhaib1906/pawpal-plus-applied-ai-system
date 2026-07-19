"""PawPal+ — pet care management app.

Core functionality for Owner, Pet, Task, and Scheduler.
Beginner-friendly implementation; no Streamlit code yet.
"""

import datetime
import uuid
from dataclasses import dataclass, field

# Allowed task priority labels. Anything else is rejected at creation/edit time.
VALID_PRIORITIES = ("low", "medium", "high")


@dataclass
class Task:
    """Represents a single unit of pet care work and its scheduling details."""

    task_name: str
    pet_name: str
    duration: int  # minutes
    priority: str  # "low" / "medium" / "high"
    start_time: str | None = None  # "HH:MM"; None lets the scheduler place it last
    recurrence: str = "once"  # "once" / "daily" / "weekly"
    day: str | None = None  # weekday this task is anchored to, e.g. "Monday"
    completed: bool = False  # whether the task has been done
    # Stable, unique identity so same-named tasks can be told apart. Auto-generated;
    # placed last so positional construction (Task(name, pet, dur, pri, ...)) is unaffected.
    task_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def __post_init__(self) -> None:
        """Validate the task's fields as soon as it is created."""
        self._validate()

    def _validate(self) -> None:
        """Validate this task's current field values."""
        self._check_fields(self.duration, self.priority)

    @staticmethod
    def _check_fields(duration: int, priority: str) -> None:
        """Ensure duration is a positive integer and priority is a known label.

        Raises ValueError on invalid input instead of silently defaulting, so
        callers learn about bad data at the point it is introduced. Static so
        proposed values can be checked before they are applied to any object.
        """
        if not isinstance(duration, int) or duration <= 0:
            raise ValueError(
                f"duration must be a positive integer (minutes), got {duration!r}"
            )
        if priority not in VALID_PRIORITIES:
            raise ValueError(
                f"priority must be one of {VALID_PRIORITIES}, got {priority!r}"
            )

    def mark_complete(self) -> None:
        """Mark this task as completed."""
        self.completed = True

    def set_duration_and_priority(self, duration: int, priority: str) -> None:
        """Set this task's duration and priority (validated atomically).

        Both values are checked before either is applied, so a rejected call
        leaves the task completely unchanged.
        """
        self._check_fields(duration, priority)
        self.duration = duration
        self.priority = priority

    def edit_task(self, **changes) -> None:
        """Update one or more of this task's fields (validated atomically).

        The proposed duration/priority are checked before any change is
        applied, so a rejected edit leaves the task completely untouched
        (no partial mutation).
        """
        proposed_duration = changes.get("duration", self.duration)
        proposed_priority = changes.get("priority", self.priority)
        self._check_fields(proposed_duration, proposed_priority)

        for field_name, value in changes.items():
            if hasattr(self, field_name):
                setattr(self, field_name, value)

    def next_occurrence(self) -> "Task | None":
        """Build the next occurrence of this task, or None if it doesn't repeat.

        Daily tasks become due today + 1 day; weekly tasks recur on the same
        weekday next week. The new task starts incomplete and gets its own
        fresh task_id (task_id is not copied), so it never collides with the
        original occurrence.
        """
        if self.recurrence not in ("daily", "weekly"):
            return None

        next_day = self.day
        if self.recurrence == "daily":
            # Due date rolls forward to tomorrow; store it as a weekday name
            # so it lines up with how the scheduler matches days.
            tomorrow = datetime.date.today() + datetime.timedelta(days=1)
            next_day = tomorrow.strftime("%A")

        return Task(
            self.task_name,
            self.pet_name,
            self.duration,
            self.priority,
            self.start_time,
            self.recurrence,
            next_day,
            completed=False,
        )

    def occurs_on(self, day: str) -> bool:
        """Return whether this task should run on the given day.

        - "daily" tasks run every day.
        - "once" and "weekly" tasks run only on their anchored day.
        - A task with no anchored day defaults to running, so simple
          tasks stay visible without extra setup.
        """
        if self.recurrence == "daily":
            return True
        if self.day is None:
            return True
        return self.day.strip().lower() == day.strip().lower()


@dataclass
class Pet:
    """Represents an individual animal and the tasks scheduled for it."""

    pet_name: str
    owner_name: str
    tasks: list[Task] = field(default_factory=list)

    def add_task(self, task: Task) -> None:
        """Attach a task to this pet."""
        self.tasks.append(task)

    def edit_task(self, task_id: str, **changes) -> None:
        """Update a task belonging to this pet (matched by unique id)."""
        for task in self.tasks:
            if task.task_id == task_id:
                task.edit_task(**changes)
                return

    def delete_task(self, task_id: str) -> None:
        """Remove a task from this pet (matched by unique id)."""
        self.tasks = [task for task in self.tasks if task.task_id != task_id]


@dataclass
class Owner:
    """Represents the person, their pets, and the scheduling constraints."""

    owner_name: str
    pets: list[Pet] = field(default_factory=list)
    available_minutes: int = 0  # daily time budget the plan should fit within
    preferences: dict = field(default_factory=dict)  # e.g. {"walk_before": "09:00"}

    def add_pet(self, pet: Pet) -> None:
        """Register a pet under this owner."""
        self.pets.append(pet)

    def edit_pet(self, pet_name: str, **changes) -> None:
        """Update a pet belonging to this owner (matched by name)."""
        for pet in self.pets:
            if pet.pet_name == pet_name:
                for field_name, value in changes.items():
                    if hasattr(pet, field_name):
                        setattr(pet, field_name, value)
                return

    def delete_pet(self, pet_name: str) -> None:
        """Remove a pet from this owner (matched by name)."""
        self.pets = [pet for pet in self.pets if pet.pet_name != pet_name]

    def all_tasks(self) -> list[Task]:
        """Return every task across all of this owner's pets."""
        tasks = []
        for pet in self.pets:
            tasks.extend(pet.tasks)
        return tasks


class Scheduler:
    """Builds a daily plan from all of an owner's tasks, sorted by time."""

    # Minutes-since-midnight value for untimed/invalid tasks, so they sort last.
    _NO_TIME = 24 * 60 + 1
    # Lower number = higher priority when ordering or trimming to a time budget.
    _PRIORITY = {"high": 0, "medium": 1, "low": 2}

    def __init__(self, owner: Owner) -> None:
        """Initialize a scheduler for a given owner."""
        self.owner = owner
        self.reasoning: str = ""  # explanation of the choices made for the last plan

    def _to_minutes(self, start_time: str | None) -> int:
        """Convert an "HH:MM" string to minutes since midnight.

        Untimed or invalid times return a large value so they sort last.
        """
        if not start_time:
            return self._NO_TIME
        try:
            hours, minutes = start_time.split(":")
            return int(hours) * 60 + int(minutes)
        except (ValueError, AttributeError):
            return self._NO_TIME

    def _priority_rank(self, priority: str) -> int:
        """Map a priority label to a sort key (lower = more important)."""
        return self._PRIORITY.get(priority, 1)

    def complete_task(self, task: Task) -> Task | None:
        """Mark a task complete; if it recurs, add its next occurrence.

        The new instance is attached to the same pet that owns the completed
        task. Returns the newly created task, or None for one-off tasks.
        """
        task.mark_complete()
        upcoming = task.next_occurrence()
        if upcoming is not None:
            for pet in self.owner.pets:
                if any(existing is task for existing in pet.tasks):
                    pet.add_task(upcoming)
                    break
        return upcoming

    def filter_tasks(
        self, tasks: list[Task], pet_name: str | None = None, status: str = "all"
    ) -> list[Task]:
        """Return tasks narrowed by pet name and/or completion status.

        pet_name: keep only this pet's tasks (None = every pet).
        status: "all" (default), "pending", or "completed".
        """
        result = tasks
        if pet_name is not None:
            result = [task for task in result if task.pet_name == pet_name]
        if status == "pending":
            result = [task for task in result if not task.completed]
        elif status == "completed":
            result = [task for task in result if task.completed]
        return result

    def sort_by_time(self, tasks: list[Task]) -> list[Task]:
        """Return tasks ordered by start time, then priority for untimed ties.

        Algorithm: a single stable sort on the composite key
        (start_minute, priority_rank). Untimed tasks (start_time is None)
        map to a large sentinel minute, so they sort last while keeping
        their relative order. Runs in O(n log n).
        """
        return sorted(
            tasks,
            key=lambda t: (self._to_minutes(t.start_time), self._priority_rank(t.priority)),
        )

    def find_conflicts(self, tasks: list[Task]) -> list[dict]:
        """Return pairs of timed tasks whose scheduled times collide.

        Two tasks conflict when one starts before the other ends (a plain
        overlap) or when they share the same start time. Each result notes
        whether the two tasks belong to the same pet.

        Algorithm: sort once by start time, precompute each task's
        [start, end) minute span, then for each task scan only the tasks
        that follow it, breaking as soon as one starts at or after the
        current task's end (the sort guarantees nothing later can overlap).
        Near-linear when few tasks overlap; O(n^2) worst case when many do.
        """
        timed = self.sort_by_time([task for task in tasks if task.start_time])

        # Parse each start time once into (task, start_minute, end_minute).
        spans = []
        for task in timed:
            start = self._to_minutes(task.start_time)
            spans.append((task, start, start + task.duration))

        conflicts = []
        for index, (first, first_start, first_end) in enumerate(spans):
            for second, second_start, _ in spans[index + 1:]:
                if second_start >= first_end:
                    break  # sorted by time, so no later task can overlap first
                conflicts.append(
                    {
                        "first": first,
                        "second": second,
                        "same_pet": first.pet_name == second.pet_name,
                        "same_time": first_start == second_start,
                    }
                )
        return conflicts

    def conflict_warning(self, tasks: list[Task]) -> str:
        """Return a short warning describing any time conflicts, or "".

        Lightweight and defensive: it never raises, so a malformed task list
        degrades to a generic notice instead of crashing the caller.
        """
        try:
            conflicts = self.find_conflicts(tasks)
        except Exception:
            return "⚠️ Could not check for time conflicts."

        if not conflicts:
            return ""

        count = len(conflicts)
        details = []
        for conflict in conflicts:
            first, second = conflict["first"], conflict["second"]
            who = "same pet" if conflict["same_pet"] else "different pets"
            when = (
                f"both at {first.start_time}"
                if conflict["same_time"]
                else f"{first.start_time} overlaps {second.start_time}"
            )
            details.append(f"{first.task_name} & {second.task_name} ({when}, {who})")
        plural = "s" if count != 1 else ""
        return f"⚠️ {count} time conflict{plural}: " + "; ".join(details)

    def generate_schedule(
        self, day: str, pet_name: str | None = None, status: str = "pending"
    ) -> list[Task]:
        """Build the day's plan: filter, fit to the time budget, and order it.

        pet_name: limit the plan to one pet's tasks (None = all pets).
        status: "pending" (default), "completed", or "all".

        Algorithm: filter by pet/status/day, then (when a budget is set)
        greedily keep tasks in priority-then-time order until the next one
        would exceed available_minutes, deferring the rest. Survivors are
        re-sorted by time for display and scanned for conflicts. The greedy
        pass is simple and explainable but not globally optimal -- it can
        leave gaps a smarter packing would fill.
        """
        # Narrow by pet and completion status.
        tasks = self.filter_tasks(self.owner.all_tasks(), pet_name=pet_name, status=status)

        # Keep only tasks that recur on this day.
        tasks = [task for task in tasks if task.occurs_on(day)]

        # Fit tasks within the owner's daily time budget (0 means "no limit").
        # Sort by priority to CHOOSE what fits; we re-sort by time for display below.
        deferred = []
        if self.owner.available_minutes > 0:
            by_importance = sorted(
                tasks,
                key=lambda t: (self._priority_rank(t.priority), self._to_minutes(t.start_time)),
            )
            kept, used = [], 0
            for task in by_importance:
                if used + task.duration <= self.owner.available_minutes:
                    kept.append(task)
                    used += task.duration
                else:
                    deferred.append(task)
            tasks = kept

        # Order the kept tasks by start time, then priority for untimed ties.
        scheduled = self.sort_by_time(tasks)

        # Flag tasks scheduled at the same time or otherwise overlapping.
        conflicts = self.find_conflicts(scheduled)

        # Build a human-readable explanation of what the scheduler did.
        scope = f" for {pet_name}" if pet_name else ""
        status_note = "" if status == "pending" else f" (status: {status})"
        reasoning = (
            f"Scheduled {len(scheduled)} task(s){scope} for {day}{status_note}, "
            f"ordered by start time then priority (untimed tasks placed last)."
        )
        if deferred:
            names = ", ".join(t.task_name for t in deferred)
            reasoning += (
                f" Deferred {len(deferred)} task(s) over the "
                f"{self.owner.available_minutes}-min budget: {names}."
            )
        if conflicts:
            parts = []
            for conflict in conflicts:
                first, second = conflict["first"], conflict["second"]
                who = "same pet" if conflict["same_pet"] else "different pets"
                if conflict["same_time"]:
                    parts.append(
                        f"{first.task_name} and {second.task_name} both at "
                        f"{first.start_time} ({who})"
                    )
                else:
                    parts.append(
                        f"{first.task_name} overlaps {second.task_name} ({who})"
                    )
            reasoning += " Time conflicts detected: " + "; ".join(parts) + "."
        self.reasoning = reasoning
        return scheduled

    def display_schedule(self, day: str) -> None:
        """Print the generated daily plan and the reasoning behind it."""
        scheduled = self.generate_schedule(day)
        print(f"Daily plan for {self.owner.owner_name} — {day}")
        if not scheduled:
            print("  (no tasks)")
        for task in scheduled:
            time_label = task.start_time if task.start_time else "  --  "
            print(
                f"  {time_label} — {task.task_name} ({task.pet_name}, "
                f"{task.duration} min) [priority: {task.priority}]"
            )
        print(self.reasoning)
