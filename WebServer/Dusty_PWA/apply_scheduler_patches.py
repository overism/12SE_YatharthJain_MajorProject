"""
apply_scheduler_patches.py
Run from your project root: python3 apply_scheduler_patches.py

Fixes two bugs in scheduler.py:
  1. Gemini only sees weekend slots because free_slots is sorted by quality
     before being sliced → weekday slots are hidden.
     Fix: pass slots to Gemini sorted chronologically.
  2. All sessions have task_id/exam_id = None so deadline_datetime_for_session()
     always returns None and the allocator never enforces deadlines.
     Fix: ask Gemini to include a due_date field; add subject-based fallback.
"""

import pathlib, sys, datetime, shutil

SCHED = pathlib.Path("scheduler.py")
if not SCHED.exists():
    sys.exit("ERROR: scheduler.py not found. Run from your project root.")

src = SCHED.read_text(encoding="utf-8")
original = src
changes = 0

# ══════════════════════════════════════════════════════════════════
# PATCH 1 — Slots shown to Gemini: chronological order, 40 slots
#
# The old code uses free_slots[:20] which is quality-sorted
# (weekends first).  Replace with chronological sort so weekday
# afternoon slots are visible to Gemini.
# ══════════════════════════════════════════════════════════════════

OLD_SLOTS = '''\
    # Build free slots summary (top 20)
    slots_summary = []
    for slot in free_slots[:20]:
        slots_summary.append({
            'date': slot['start'].strftime('%Y-%m-%d'),
            'start_time': slot['start'].strftime('%H:%M'),
            'end_time': slot['end'].strftime('%H:%M'),
            'duration_minutes': slot['duration_minutes'],
            'quality': slot['quality']
        })'''

NEW_SLOTS = '''\
    # Build free slots summary — sorted CHRONOLOGICALLY so Gemini
    # sees weekday afternoon slots, not just quality-ranked weekends.
    slots_summary = []
    for slot in sorted(free_slots, key=lambda s: s["start"])[:40]:
        slots_summary.append({
            'date': slot['start'].strftime('%Y-%m-%d'),
            'day_of_week': slot['start'].strftime('%A'),
            'start_time': slot['start'].strftime('%H:%M'),
            'end_time': slot['end'].strftime('%H:%M'),
            'duration_minutes': slot['duration_minutes'],
        })'''

if OLD_SLOTS in src:
    src = src.replace(OLD_SLOTS, NEW_SLOTS, 1)
    changes += 1
    print("✓ PATCH 1 applied: free slots now passed to Gemini in chronological order")
else:
    print("⚠ PATCH 1 skipped: slots summary block not found (may already be patched)")

# ══════════════════════════════════════════════════════════════════
# PATCH 2 — Gemini prompt: add due_date field + explicit deadline rule
#
# Replace the OUTPUT FORMAT section so Gemini is instructed to
# populate due_date from the task/exam due date.
# ══════════════════════════════════════════════════════════════════

OLD_FORMAT = '''\
    {{
      "study_sessions": [
        {{
          "title": "Chemistry Module 8 Revision",
          "subject": "Chemistry",
          "duration_minutes": 90,
          "priority": "high",
          "strategy": "Spaced Repetition",
          "reasoning": "Exam in 10 days - need consistent revision",
          "suggested_date": "2024-12-15",
          "suggested_start_time": "14:00",
          "task_id": 123,
          "exam_id": null
        }}
      ],
      "reasoning": "Brief explanation of how you distributed sessions",
      "techniques_used": ["Spaced Repetition", "Active Recall", "Interleaving"]
    }}

- title: Meaningful name indicating what to study (NOT "Deadline: Thursday")
- subject: Must match one of the user's subjects
- duration_minutes: 45-120 depending on technique and slot availability
- priority: "high" (≤3 days), "medium" (4-7 days), "normal" (>7 days)
- strategy: One of the evidence-based techniques above
- reasoning: Why this session is scheduled this way
- suggested_date: YYYY-MM-DD format (must be one of the available dates in slots)
- suggested_start_time: HH:MM format (must fit within an available slot)
- task_id: The ID of the task this session relates to (if any)
- exam_id: The ID of the exam this session relates to (if any)

IMPORTANT: Make sure suggested_date and suggested_start_time align with the available free slots provided.
Use 24-hour HH:MM strings for suggested_start_time (for example "14:30", not "2:30 PM").'''

NEW_FORMAT = '''\
    {{
      "study_sessions": [
        {{
          "title": "Chemistry Module 8 Revision",
          "subject": "Chemistry",
          "duration_minutes": 90,
          "priority": "high",
          "strategy": "Spaced Repetition",
          "reasoning": "Exam in 10 days - need consistent revision",
          "suggested_date": "2024-12-15",
          "suggested_start_time": "14:00",
          "due_date": "2024-12-25",
          "task_id": 123,
          "exam_id": null
        }}
      ],
      "reasoning": "Brief explanation of how you distributed sessions",
      "techniques_used": ["Spaced Repetition", "Active Recall", "Interleaving"]
    }}

- title: Meaningful name indicating what to study (NOT "Deadline: Thursday")
- subject: Must match one of the user's subjects
- duration_minutes: 45-120 depending on technique and slot availability
- priority: "high" (≤3 days), "medium" (4-7 days), "normal" (>7 days)
- strategy: One of the evidence-based techniques above
- reasoning: Why this session is scheduled this way
- suggested_date: YYYY-MM-DD format (must be one of the available dates in slots)
- suggested_start_time: HH:MM format (must fit within an available slot)
- due_date: YYYY-MM-DD of the task or exam this session is preparing for.
  MANDATORY — copy this directly from the task/exam due date listed above.
  Every session MUST end before this date. If no specific task, use null.
- task_id: The ID of the task this session relates to (if any)
- exam_id: The ID of the exam this session relates to (if any)

IMPORTANT:
- suggested_date and suggested_start_time MUST match one of the available free slots.
- Use 24-hour HH:MM strings for suggested_start_time (e.g. "14:30", not "2:30 PM").
- NEVER schedule a session on or after its due_date. The session must END before midnight
  of the due_date.
- Prefer weekday afternoon slots (listed in the free slots above) before weekend slots
  when both are available — students need consistent daily study, not just weekend cramming.'''

if OLD_FORMAT in src:
    src = src.replace(OLD_FORMAT, NEW_FORMAT, 1)
    changes += 1
    print("✓ PATCH 2 applied: Gemini prompt updated with due_date field and deadline rule")
else:
    print("⚠ PATCH 2 skipped: output format block not found (may already be patched)")

# ══════════════════════════════════════════════════════════════════
# PATCH 3 — deadline_datetime_for_session(): check due_date field
#           and add subject-based exam matching as fallback
# ══════════════════════════════════════════════════════════════════

OLD_DEADLINE = '''\
def deadline_datetime_for_session(session: Dict, user_data: Dict) -> Optional[datetime]:
    """Find the strict latest allowed end datetime for a generated session."""
    explicit = parse_deadline_date(
        session.get('deadline') or session.get('due_date') or session.get('exam_date')
    )
    if explicit:
        return datetime.combine(explicit, datetime.min.time())

    task_id = session.get('task_id')
    exam_id = session.get('exam_id')

    if task_id:
        for task in user_data.get('tasks', []):
            if str(task.get('id')) == str(task_id):
                due = parse_deadline_date(task.get('due_date'))
                if due:
                    return datetime.combine(due, datetime.min.time())

    if exam_id:
        for exam in user_data.get('exams', []):
            if str(exam.get('id')) == str(exam_id):
                due = parse_deadline_date(exam.get('exam_date'))
                if due:
                    return datetime.combine(due, datetime.min.time())

    return None'''

NEW_DEADLINE = '''\
def deadline_datetime_for_session(session: Dict, user_data: Dict) -> Optional[datetime]:
    """
    Find the strict latest allowed END datetime for a generated session.

    Priority:
    1. Explicit due_date / deadline / exam_date on the session dict
       (Gemini is now instructed to always populate due_date).
    2. task_id lookup in user_data['tasks'].
    3. exam_id lookup in user_data['exams'].
    4. Subject-name fuzzy match against exams — catches the common case
       where Gemini returns task_id=None but the session subject matches
       a known exam.
    """
    # 1 — explicit field on the session
    explicit = parse_deadline_date(
        session.get('due_date') or session.get('deadline') or session.get('exam_date')
    )
    if explicit:
        return datetime.combine(explicit, datetime.min.time())

    task_id = session.get('task_id')
    exam_id = session.get('exam_id')

    # 2 — task lookup
    if task_id:
        for task in user_data.get('tasks', []):
            if str(task.get('id')) == str(task_id):
                due = parse_deadline_date(task.get('due_date'))
                if due:
                    return datetime.combine(due, datetime.min.time())

    # 3 — exam lookup by id
    if exam_id:
        for exam in user_data.get('exams', []):
            if str(exam.get('id')) == str(exam_id):
                due = parse_deadline_date(exam.get('exam_date'))
                if due:
                    return datetime.combine(due, datetime.min.time())

    # 4 — subject-based fuzzy match (handles task_id = None)
    session_subject = (session.get('subject') or '').lower().strip()
    if session_subject:
        earliest: Optional[date] = None

        # Check tasks first
        for task in user_data.get('tasks', []):
            task_subj = (task.get('subject') or '').lower().strip()
            if task_subj and (task_subj in session_subject or session_subject in task_subj):
                due = parse_deadline_date(task.get('due_date'))
                if due and (earliest is None or due < earliest):
                    earliest = due

        # Then check exams (higher priority — stricter deadline)
        for exam in user_data.get('exams', []):
            exam_subj = (exam.get('subject') or '').lower().strip()
            if exam_subj and (exam_subj in session_subject or session_subject in exam_subj):
                due = parse_deadline_date(exam.get('exam_date'))
                if due and (earliest is None or due < earliest):
                    earliest = due

        if earliest:
            return datetime.combine(earliest, datetime.min.time())

    return None'''

if OLD_DEADLINE in src:
    src = src.replace(OLD_DEADLINE, NEW_DEADLINE, 1)
    changes += 1
    print("✓ PATCH 3 applied: deadline_datetime_for_session() now uses subject matching fallback")
else:
    print("⚠ PATCH 3 skipped: deadline function not found (may already be patched)")

# ══════════════════════════════════════════════════════════════════
# PATCH 4 — NON-NEGOTIABLE RULE in the prompt: add a weekday
#           preference instruction alongside the deadline rule
#           (the prompt already has the rule; just strengthen it)
# ══════════════════════════════════════════════════════════════════

OLD_NONNEG = '''\
NON-NEGOTIABLE RULE:
Every study session MUST occur before the assessment deadline.
Do not create sessions on or after the deadline.'''

NEW_NONNEG = '''\
NON-NEGOTIABLE RULES:
1. Every study session MUST occur before the assessment deadline (before its due_date).
   Do not create sessions on or after the due_date.
2. DO NOT cluster all sessions on weekends. Use the weekday afternoon slots provided
   (typically 16:00–22:00) for regular study. Weekend sessions are for longer blocks.
3. Sessions must be spread from TODAY up to (but not including) each deadline date.
   If an exam is on June 24, the last session for it must be on June 23 or earlier.'''

if OLD_NONNEG in src:
    src = src.replace(OLD_NONNEG, NEW_NONNEG, 1)
    changes += 1
    print("✓ PATCH 4 applied: Non-negotiable rules strengthened in prompt")
else:
    print("⚠ PATCH 4 skipped: non-negotiable rule not found (may already be patched)")

# ══════════════════════════════════════════════════════════════════
# Write out
# ══════════════════════════════════════════════════════════════════

if changes == 0:
    print("\nNo changes made.")
    sys.exit(0)

backup = SCHED.with_suffix(f".py.bak_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}")
backup.write_text(original, encoding="utf-8")
print(f"\nBackup written to {backup}")
SCHED.write_text(src, encoding="utf-8")
print(f"scheduler.py updated ({changes}/4 patches applied).")
