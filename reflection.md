# PawPal+ Project Reflection

## 1. System Design

**Core Actions**

- Add and manage pets
- Add and manage tasks (feedings, walks, medications, appointments)
- View today's schedule or upcoming tasks

**a. Initial design**

- Briefly describe your initial UML design.
--> my initial UML design 4 core classes. pet, owner, task and schedule.

The Owner class manages pet information. The Pet class stores details about each pet. The Task class stores pet care tasks, including the task name, duration, and priority. The Scheduler class organizes tasks and creates a daily schedule.

- What classes did you include, and what responsibilities did you assign to each?
-->

**Owner**
- Attributes: owner_name (string), pet_names (list of string)
- Methods: add_owner(), edit_owner(), delete_owner(), add_pet(pet_name)
- Responsibility: represents the person and the pets registered under them.

**Pet**
- Attributes: pet_name (string), owner_name (string)
- Methods: add_pet(), edit_pet(), delete_pet()
- Responsibility: represents an individual animal and links back to its owner.

**Task**
- Attributes: task_name (string), pet_name (string), duration (int, minutes), priority (string: low / medium / high)
- Methods: add_task(), set_duration_and_priority(), edit_task(), delete_task(), display_tasks_for_day(day)
- Responsibility: represents a single unit of pet care work and its scheduling details.

**Scheduler**
- Attributes: tasks (list of Task), pet_name (string)
- Methods: generate_schedule(), display_schedule()
- Responsibility: orders and times the tasks into a daily plan and displays it.


**b. Design changes**

- Did your design change during implementation?
- If yes, describe at least one change and why you made it.

--> Yes. After reviewing the design, I changed the relationships between the classes. Pets now store their own tasks, and Owners store Pet objects instead of only pet names. I made this change because it creates cleaner connections between classes and makes it easier for the Scheduler to access and organize tasks.

I also added start_time and recurrence fields to Task so the system can support scheduling, conflict detection, and recurring tasks.
---

## 2. Scheduling Logic and Tradeoffs

**a. Constraints and priorities**

- What constraints does your scheduler consider (for example: time, priority, preferences)?
--> Time (start time): tasks are ordered chronologically, and overlap clashes are flagged as conflicts
--> Priority: breaks ties between tasks and decides who gets kept when time runs short
--> Time budget : when set, the plan fits high-priority tasks first and defers the rest
--> Day / recurrence: only tasks due that day survive, daily run every day, weekly/once only on their anchored day

- How did you decide which constraints mattered most?
--> I ranked constraints by what a pet owner can't compromise on. Priority ranks highest because the whole point is guaranteeing critical care (meds, feeding) happens even on a packed day.


**b. Tradeoffs**

- Describe one tradeoff your scheduler makes.
--> When tasks exceed the owner's time budget, the scheduler keeps the highest priority tasks and drops the rest entirely.

- Why is that tradeoff reasonable for this scenario?
--> A pet owner cares most that critical care (meds, feeding) always makes the cut, and a simple, predictable "high-priority first" rule is far easier to trust.

---

## 3. AI Collaboration

**a. How you used AI**

- How did you use AI tools during this project (for example: design brainstorming, debugging, refactoring)?
--> AI was used in: UML Design, Testing, UI Integration and writing code.

- What kinds of prompts or questions were most helpful?
--> "Based on my skeleton, how should the Scheduler retrieve tasks from the Owner?"

**b. Judgment and verification**

- Describe one moment where you did not accept an AI suggestion as-is.
--> rejected preference as a class
---

## 4. Testing and Verification

**a. What you tested**

- What behaviors did you test?
--> I tested sorting , recurring tasks , and conflict detection.

- Why were these tests important?
--> These are the core jobs of the scheduler, so if any of them break the daily plan would be wrong or misleading. Testing them makes sure the app can be trusted.

**b. Confidence**

- How confident are you that your scheduler works correctly?
--> ⭐⭐⭐⭐⭐ (5/5 Stars)
---

## 5. Reflection

**a. What went well**

- What part of this project are you most satisfied with?
--> The scheduler's core logic (sorting, conflict detection, recurring tasks) turned out solid enough that I could build directly on top of it for Project 4 without needing to touch it. When I later added task IDs, input validation, and a live conflicts UI, all 27 original tests kept passing without changes, which told me the original design held up. I'm also glad I added a real AI agent on top of it for Project 4 (an agentic conflict resolver using Gemini) instead of just a surface-level AI feature. It actually reads the scheduler's own conflict output, retrieves relevant care tips, proposes a fix, and checks its own work by re-running the conflict check, so it's genuinely integrated into the app's logic rather than a bolted-on script.

**b. What you would improve**

- If you had another iteration, what would you improve or redesign?
--> I'd add persistence (the app still loses everything on refresh) and give tasks a concept of "how movable" they are, since right now the AI agent treats a meds task and a play-time task as equally easy to reschedule, which isn't realistic for pet care. I'd also replace the keyword-based tip retrieval in Project 4 with a proper embedding search if the tips file ever grew past a handful of entries, since keyword matching only works because the tip set is still small.

**c. Key takeaway**

- What is one important thing you learned about designing systems or working with AI on this project?
--> The biggest lesson came from Project 4: a fallback safety net can quietly hide a real bug. My AI agent was silently using its fallback rule instead of calling Gemini for a while, and nothing crashed, so it looked like it was "working." It took real debugging, not guessing, to trace it back to a missing dependency and a retired model name. That taught me that in AI-integrated systems, "it didn't crash" and "it's actually working as intended" are two different things, and a system needs a way to tell you which one is true.