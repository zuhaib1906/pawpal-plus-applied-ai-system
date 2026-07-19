import streamlit as st
from pawpal_system import Owner, Pet, Task, Scheduler

st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="centered")

st.title("🐾 PawPal+")

st.info(
    "⚠️ **Demo only — nothing is saved.** Your pets, tasks, and schedule live in "
    "memory for this session and are lost when you refresh or close the tab.",
    icon="⚠️",
)

st.markdown(
    """
Welcome to the PawPal+ starter app.

This file is intentionally thin. It gives you a working Streamlit app so you can start quickly,
but **it does not implement the project logic**. Your job is to design the system and build it.

Use this app as your interactive demo once your backend classes/functions exist.
"""
)

with st.expander("Scenario", expanded=True):
    st.markdown(
        """
**PawPal+** is a pet care planning assistant. It helps a pet owner plan care tasks
for their pet(s) based on constraints like time, priority, and preferences.

You will design and implement the scheduling logic and connect it to this Streamlit UI.
"""
    )

with st.expander("What you need to build", expanded=True):
    st.markdown(
        """
At minimum, your system should:
- Represent pet care tasks (what needs to happen, how long it takes, priority)
- Represent the pet and the owner (basic info and preferences)
- Build a plan/schedule for a day that chooses and orders tasks based on constraints
- Explain the plan (why each task was chosen and when it happens)
"""
    )

st.divider()

st.subheader("Quick Demo Inputs")
owner_name = st.text_input("Owner name", value="Jordan")

# Create the Owner once and keep it across reruns (see st.session_state).
if "owner" not in st.session_state:
    st.session_state.owner = Owner(owner_name)
owner = st.session_state.owner
owner.owner_name = owner_name  # keep in sync with the input box

# One Scheduler for the whole page; created early so add/edit handlers can reuse
# its conflict detection for immediate warnings.
scheduler = Scheduler(owner)


def _task_label(task: Task) -> str:
    """Build the readable label used to identify a task in select boxes."""
    return (
        f"{task.task_name} — {task.pet_name} "
        f"({task.start_time or 'no time'}, {'done' if task.completed else 'pending'})"
    )


def _describe_conflict(conflict: dict) -> str:
    """Turn one find_conflicts() entry into a readable one-line description."""
    first, second = conflict["first"], conflict["second"]
    who = "same pet" if conflict["same_pet"] else "different pets"
    when = (
        f"both at {first.start_time}"
        if conflict["same_time"]
        else f"{first.start_time} overlaps {second.start_time}"
    )
    return (
        f"{first.task_name} ({first.pet_name}) & "
        f"{second.task_name} ({second.pet_name}) — {when}, {who}"
    )


def _conflicts_for(task: Task) -> list[dict]:
    """Return the current conflicts (across all tasks) that involve `task`."""
    return [
        conflict
        for conflict in scheduler.find_conflicts(owner.all_tasks())
        if task.task_id in (conflict["first"].task_id, conflict["second"].task_id)
    ]


st.markdown("### Pets")
pet_name = st.text_input("Pet name", value="Mochi")

if st.button("Add pet"):
    # Add the pet only if one with that name isn't already registered.
    if any(pet.pet_name == pet_name for pet in owner.pets):
        st.warning(f"{pet_name} is already added.")
    else:
        owner.add_pet(Pet(pet_name, owner.owner_name))

if owner.pets:
    st.write("Pets:", ", ".join(pet.pet_name for pet in owner.pets))
else:
    st.info("No pets yet. Add one above.")

st.markdown("### Tasks")
st.caption("Add a few tasks to a pet. These feed into the scheduler below.")

col1, col2, col3, col4 = st.columns(4)
with col1:
    task_title = st.text_input("Task title", value="Morning walk")
with col2:
    duration = st.number_input("Duration (minutes)", min_value=1, max_value=240, value=20)
with col3:
    priority = st.selectbox("Priority", ["low", "medium", "high"], index=2)
with col4:
    start_time = st.text_input("Start time (HH:MM)", value="08:00")

# Pick which pet the task belongs to.
pet_choices = [pet.pet_name for pet in owner.pets]
selected_pet_name = st.selectbox("Assign to pet", pet_choices) if pet_choices else None

if st.button("Add task"):
    if selected_pet_name is None:
        st.warning("Add a pet first, then assign tasks to it.")
    else:
        # Find the chosen Pet and attach a real Task to it. Task validates its
        # own fields, so surface any problem instead of silently accepting it.
        pet = next(p for p in owner.pets if p.pet_name == selected_pet_name)
        try:
            new_task = Task(
                task_title,
                pet.pet_name,
                int(duration),
                priority,
                start_time or None,
            )
            pet.add_task(new_task)
            # Immediate (non-blocking) conflict warning for the task just added.
            involved = _conflicts_for(new_task)
            if involved:
                st.warning(
                    "⚠️ Task added, but it conflicts with:\n\n"
                    + "\n".join(f"- {_describe_conflict(c)}" for c in involved)
                )
        except ValueError as err:
            st.error(f"Could not add task: {err}")

# One-shot message carried across a st.rerun() (e.g. after editing a task).
_flash = st.session_state.pop("flash", None)
if _flash:
    getattr(st, _flash["kind"])(_flash["msg"])


def _find_task(task_id: str):
    """Return (pet, task) for a task_id, or (None, None) if not found."""
    for p in owner.pets:
        for t in p.tasks:
            if t.task_id == task_id:
                return p, t
    return None, None


if owner.all_tasks():
    st.write("Current tasks")

    # Map each task's readable label to its unique id (used by the conflicts
    # section and the "Manage a task" editor below).
    task_options = {_task_label(t): t.task_id for t in owner.all_tasks()}

    # Live conflicts across PENDING tasks — drives both the badge and the
    # section below, so they always agree and reflect the current state on every
    # render. Completed tasks are excluded: an overlap with something already
    # done isn't a real scheduling problem.
    pending_tasks = scheduler.filter_tasks(owner.all_tasks(), status="pending")
    all_conflicts = scheduler.find_conflicts(pending_tasks)

    # Filter controls — feed straight into Scheduler.filter_tasks().
    fcol1, fcol2 = st.columns(2)
    with fcol1:
        pet_filter = st.selectbox(
            "Filter by pet", ["All pets"] + [pet.pet_name for pet in owner.pets]
        )
    with fcol2:
        status_filter = st.selectbox("Filter by status", ["all", "pending", "completed"])

    filtered = scheduler.filter_tasks(
        owner.all_tasks(),
        pet_name=None if pet_filter == "All pets" else pet_filter,
        status=status_filter,
    )
    filtered = scheduler.sort_by_time(filtered)

    if filtered:
        # Summary metrics give the table a polished, dashboard-style header.
        total_minutes = sum(t.duration for t in filtered)
        done_count = sum(1 for t in filtered if t.completed)
        mcol1, mcol2, mcol3, mcol4 = st.columns(4)
        mcol1.metric("Tasks", len(filtered))
        mcol2.metric("Total time", f"{total_minutes} min")
        mcol3.metric("Completed", f"{done_count}/{len(filtered)}")
        # Conflict badge — reflects all tasks, so it flags trouble even when the
        # current filter hides the conflicting task.
        mcol4.metric(
            "⚠️ Conflicts" if all_conflicts else "Conflicts", len(all_conflicts)
        )

        st.table(
            [
                {
                    "✓": "✅" if t.completed else "⏳",
                    "Start": t.start_time or "--",
                    "Task": t.task_name,
                    "Pet": t.pet_name,
                    "Duration": f"{t.duration} min",
                    "Priority": t.priority.capitalize(),
                }
                for t in filtered
            ]
        )
    else:
        st.info("No tasks match the current filters.")

    # ------------------------------------------------------------------
    # Conflicts: always reflects the live state of all tasks. Distinct and
    # hard to miss when conflicts exist; quiet when there are none.
    # ------------------------------------------------------------------
    if not all_conflicts:
        st.success("No time conflicts. ✅")
    else:
        plural = "s" if len(all_conflicts) != 1 else ""
        with st.expander(f"⚠️ {len(all_conflicts)} time conflict{plural} — review", expanded=True):
            st.caption(
                "These tasks overlap. Edit or delete either one, or leave them "
                "as-is to keep both."
            )
            for i, conflict in enumerate(all_conflicts):
                first, second = conflict["first"], conflict["second"]
                st.markdown(f"**{i + 1}.** {_describe_conflict(conflict)}")
                a1, a2, a3, a4 = st.columns(4)
                # Edit jumps the "Manage a task" editor below to that task.
                if a1.button(f"Edit {first.task_name}", key=f"cf_edit_first_{i}"):
                    st.session_state["manage_task_select"] = _task_label(first)
                    st.rerun()
                if a2.button(f"Edit {second.task_name}", key=f"cf_edit_second_{i}"):
                    st.session_state["manage_task_select"] = _task_label(second)
                    st.rerun()
                if a3.button(f"Delete {first.task_name}", key=f"cf_del_first_{i}"):
                    pet, _ = _find_task(first.task_id)
                    if pet is not None:
                        pet.delete_task(first.task_id)
                    st.rerun()
                if a4.button(f"Delete {second.task_name}", key=f"cf_del_second_{i}"):
                    pet, _ = _find_task(second.task_id)
                    if pet is not None:
                        pet.delete_task(second.task_id)
                    st.rerun()

    # ------------------------------------------------------------------
    # Manage a task: mark complete, edit time/duration/priority, or delete.
    # ------------------------------------------------------------------
    st.markdown("#### Manage a task")

    # Drop a stale preselection (e.g. the "Edit" target was just deleted) so the
    # selectbox never errors on a value that is no longer an option.
    if st.session_state.get("manage_task_select") not in task_options:
        st.session_state.pop("manage_task_select", None)

    chosen_label = st.selectbox("Select a task", list(task_options), key="manage_task_select")
    chosen_id = task_options[chosen_label]
    chosen_pet, chosen_task = _find_task(chosen_id)

    if chosen_task is not None:
        ecol1, ecol2, ecol3 = st.columns(3)
        with ecol1:
            new_duration = st.number_input(
                "Duration (minutes)",
                min_value=1,
                max_value=240,
                value=chosen_task.duration,
                key=f"dur_{chosen_id}",
            )
        with ecol2:
            new_priority = st.selectbox(
                "Priority",
                ["low", "medium", "high"],
                index=["low", "medium", "high"].index(chosen_task.priority),
                key=f"pri_{chosen_id}",
            )
        with ecol3:
            new_start = st.text_input(
                "Start time (HH:MM)",
                value=chosen_task.start_time or "",
                key=f"start_{chosen_id}",
            )

        bcol1, bcol2, bcol3 = st.columns(3)
        with bcol1:
            if st.button("Save changes"):
                try:
                    chosen_pet.edit_task(
                        chosen_id,
                        duration=int(new_duration),
                        priority=new_priority,
                        start_time=new_start or None,
                    )
                    # Immediate conflict check for the just-edited task; carried
                    # across the rerun via the flash message.
                    involved = _conflicts_for(chosen_task)
                    if involved:
                        st.session_state["flash"] = {
                            "kind": "warning",
                            "msg": "⚠️ Task updated, but it now conflicts with:\n\n"
                            + "\n".join(f"- {_describe_conflict(c)}" for c in involved),
                        }
                    else:
                        st.session_state["flash"] = {"kind": "success", "msg": "Task updated."}
                    st.rerun()
                except ValueError as err:
                    st.error(f"Could not update task: {err}")
        with bcol2:
            if st.button("Mark complete"):
                created = scheduler.complete_task(chosen_task)
                if created is not None:
                    st.success(
                        f"Marked complete. Next {chosen_task.recurrence} occurrence "
                        f"of “{created.task_name}” was scheduled."
                    )
                else:
                    st.success("Marked complete.")
                st.rerun()
        with bcol3:
            if st.button("Delete task"):
                chosen_pet.delete_task(chosen_id)
                st.rerun()
else:
    st.info("No tasks yet. Add one above.")

# Manage pets: remove a pet (and all of its tasks) from the owner.
if owner.pets:
    st.markdown("#### Manage pets")
    pet_to_delete = st.selectbox(
        "Select a pet to delete", [pet.pet_name for pet in owner.pets]
    )
    if st.button("Delete pet"):
        owner.delete_pet(pet_to_delete)
        st.rerun()

st.divider()

st.subheader("Build Schedule")
st.caption("Generates a daily plan from all tasks, sorted by start time.")

day = st.text_input("Day", value="Monday")

if st.button("Generate schedule"):
    scheduled = scheduler.generate_schedule(day)
    if not scheduled:
        st.info("No tasks to schedule yet.")
    else:
        st.markdown(f"#### 📅 Daily plan for {owner.owner_name} — {day}")

        planned_minutes = sum(t.duration for t in scheduled)
        pcol1, pcol2 = st.columns(2)
        pcol1.metric("Scheduled tasks", len(scheduled))
        pcol2.metric("Planned time", f"{planned_minutes} min")

        st.table(
            [
                {
                    "Start": task.start_time or "--",
                    "Task": task.task_name,
                    "Pet": task.pet_name,
                    "Duration": f"{task.duration} min",
                    "Priority": task.priority.capitalize(),
                }
                for task in scheduled
            ]
        )

        # Surface any overlapping/clashing tasks via conflict_warning().
        warning = scheduler.conflict_warning(scheduled)
        if warning:
            st.warning(warning)
        else:
            st.success("No time conflicts. ✅")

        st.caption(scheduler.reasoning)
