"""
Intelligent Scheduling Engine for Dusty PWA

This module provides:
- NLP parsing for freeform text input
- Priority scoring based on deadlines, workload, and urgency
- Smart time slot allocation with conflict detection
- Gemini-powered study schedule generation
- Schedule generation respecting user preferences

Designed for Year 11/12 HSC students.
"""

import re
import json
from datetime import datetime, timedelta, date, timezone
from typing import Optional, List, Dict, Any
from collections import defaultdict

# Gemini integration - imported when needed to avoid circular imports
_gemini_client = None

def _get_gemini_client():
    """Lazy load Gemini client to avoid circular imports."""
    global _gemini_client
    if _gemini_client is None:
        try:
            from Chat.gemini_client import ask_gemini_json
            _gemini_client = ask_gemini_json
        except ImportError:
            return None
    return _gemini_client


# ============== CONSTANTS ==============

DAYS_OF_WEEK = {
    'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
    'friday': 4, 'saturday': 5, 'sunday': 6
}

# Default colors if user has none (fallback only - should use database colors)
DEFAULT_COLORS = {
    'default': '#f5761b',
    'orange': '#f5761b',
    'blue': '#3498db',
    'green': '#27ae60',
    'red': '#e74c3c',
    'purple': '#9b59b6',
    'yellow': '#f1c40f',
    'amber': '#f39c12',
    'teal': '#1abc9c',
    'pink': '#e91e63',
    'brown': '#795548'
}


# ============== DATABASE HELPERS ==============

def get_user_subjects_from_db(conn, user_id: int) -> List[Dict]:
    """
    Load user's subjects and their colours from the database.
    This is the PRIMARY source - no hardcoded subjects.
    """
    try:
        rows = conn.execute("""
            SELECT subjectID, subjectName, colourScheme
            FROM subjects
            WHERE userID = ?
            ORDER BY sortOrder, subjectID
        """, (user_id,)).fetchall()

        subjects = []
        for row in rows:
            colour = row['colourScheme'] or 'default'
            # Normalize colour name to lowercase
            colour_lower = colour.lower()
            subjects.append({
                'subjectID': row['subjectID'],
                'subjectName': row['subjectName'],
                'colour': DEFAULT_COLORS.get(colour_lower, DEFAULT_COLORS['default']),
                'colourName': colour
            })

        print(f"[SCHEDULER] Loaded {len(subjects)} subjects from database for user {user_id}")
        return subjects
    except Exception as e:
        print(f"[SCHEDULER] Error loading subjects: {e}")
        return []


def get_subject_colour_map(subjects: List[Dict]) -> Dict[str, str]:
    """Build a map of subject name -> colour from loaded subjects."""
    colour_map = {}
    for subj in subjects:
        name_lower = subj['subjectName'].lower()
        colour_map[name_lower] = subj['colour']
        # Also map without spaces
        colour_map[subj['subjectName'].replace(' ', '').lower()] = subj['colour']
    return colour_map


# ============== FREE SLOT CALCULATION ==============

def calculate_free_time_windows(
    conn,
    user_id: int,
    start_date: datetime,
    end_date: datetime,
    user_preferences: dict
) -> List[Dict]:
    """
    Calculate all free time windows between start_date and end_date.

    A free time window is:
    - Not occupied by existing calendar events
    - Not occupied by existing generated study sessions
    - Within reasonable study hours
    - Respecting sleep times

    Returns list of free slots with start/end times.
    """
    print(f"[SCHEDULER] Calculating free windows from {start_date} to {end_date}")

    # Get user preferences
    study_start = user_preferences.get('study_start', 8)
    study_end = user_preferences.get('study_end', 22)
    sleep_start = user_preferences.get('sleep_start', 22)
    sleep_end = user_preferences.get('sleep_end', 7)
    school_start = user_preferences.get('school_start', 9)
    school_end = user_preferences.get('school_end', 15)

    print(f"[SCHEDULER] Study hours: {study_start}:00 - {study_end}:00")
    print(f"[SCHEDULER] Sleep hours: {sleep_start}:00 - {sleep_end}:00")
    print(f"[SCHEDULER] School hours: {school_start}:00 - {school_end}:00")

    # Get existing events in the date range
    existing_events = []
    try:
        rows = conn.execute("""
            SELECT eventID, title, startTime, endTime, source
            FROM events
            WHERE userID = ?
              AND isDeleted = 0
              AND startTime >= ?
              AND endTime <= ?
            ORDER BY startTime
        """, (user_id, start_date.isoformat(), end_date.isoformat())).fetchall()

        for row in rows:
            try:
                start = parse_calendar_dt(row['startTime'])
                end = parse_calendar_dt(row['endTime'])
                if start and end:
                    existing_events.append({
                        'id': row['eventID'],
                        'title': row['title'],
                        'start': start,
                        'end': end,
                        'source': row['source']
                    })
            except Exception as e:
                print(f"[SCHEDULER] Error parsing event: {e}")
                continue

        print(f"[SCHEDULER] Found {len(existing_events)} existing events")
    except Exception as e:
        print(f"[SCHEDULER] Error loading events: {e}")

    # Build timeline and find free slots
    free_slots = []
    # Make timezone-aware to match event['start'] from database (which uses UTC)
    if start_date.tzinfo is None:
        start_date = start_date.replace(tzinfo=timezone.utc)
    if end_date.tzinfo is None:
        end_date = end_date.replace(tzinfo=timezone.utc)
    current = start_date.replace(hour=study_start, minute=0, second=0, microsecond=0)

    # If current time is later than study start, adjust
    if current < start_date:
        current = start_date
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)

    while current < end_date:
        # Skip sleep hours
        if sleep_start > sleep_end:
            # Sleep crosses midnight
            if current.hour >= sleep_start or current.hour < sleep_end:
                current = (current + timedelta(days=1)).replace(hour=study_start)
                continue
        else:
            if sleep_start <= current.hour < sleep_end:
                current = current.replace(hour=study_end)
                if current.hour < study_start:
                    current = (current + timedelta(days=1)).replace(hour=study_start)
                continue

        # Skip school hours on weekdays
        if current.weekday() < 5:  # Monday-Friday
            if school_start <= current.hour < school_end:
                current = current.replace(hour=school_end, minute=0, second=0, microsecond=0)
                continue

        # Check if within study hours
        if current.hour < study_start:
            current = current.replace(hour=study_start, minute=0)
        if current.hour >= study_end:
            current = (current + timedelta(days=1)).replace(hour=study_start, minute=0)
            continue

        # Find next occupied time
        slot_end = end_date
        for event in existing_events:
            if event['start'] > current and event['start'] <= slot_end:
                slot_end = event['start']

        day_end = current.replace(hour=study_end, minute=0, second=0, microsecond=0)
        if slot_end > day_end:
            slot_end = day_end

        # If we have a valid free slot (at least 30 minutes)
        if (slot_end - current).total_seconds() >= 1800:
            # Score the slot based on quality
            quality_score = score_time_slot(current, current.weekday())

            free_slots.append({
                'start': current,
                'end': slot_end,
                'duration_minutes': int((slot_end - current).total_seconds() / 60),
                'quality': quality_score
            })

        # Move to next potential slot
        current = slot_end + timedelta(minutes=30)  # Check every 30 mins
        if current.hour >= study_end:
            current = (current + timedelta(days=1)).replace(hour=study_start, minute=0)

    # Sort by quality (higher is better)
    free_slots.sort(key=lambda x: x['quality'], reverse=True)

    print(f"[SCHEDULER] Found {len(free_slots)} free slots")
    return free_slots


def score_time_slot(dt: datetime, weekday: int) -> float:
    """
    Score a time slot based on quality preferences.

    Prefer:
    - Afternoon study blocks (14:00-17:00)
    - Weekend longer sessions
    - Evening revision (16:00-19:00)

    Avoid:
    - Late-night sessions (after 21:00)
    - Early morning (before 7:00)
    """
    score = 50.0  # Base score

    hour = dt.hour

    # Prefer afternoon (14-17)
    if 14 <= hour < 17:
        score += 20
    # Good evening (17-19)
    elif 17 <= hour < 19:
        score += 15
    # Good morning (8-10)
    elif 8 <= hour < 10:
        score += 10
    # Late night is bad
    elif hour >= 21:
        score -= 30
    # Early morning is okay
    elif hour < 7:
        score -= 10

    # Weekend bonus
    if weekday >= 5:  # Saturday or Sunday
        score += 15

    return score


# ============== DATA COLLECTION ==============

def collect_user_data(conn, user_id: int, user_preferences: dict) -> Dict:
    """
    Collect all user data needed for schedule generation.

    Returns:
    - tasks: List of pending tasks
    - exams: List of upcoming exams
    - events: List of existing calendar events
    - subjects: List of user subjects with colours
    - free_slots: Calculated free time windows
    """
    print(f"\n{'='*60}")
    print(f"[SCHEDULER] Collecting data for user {user_id}")
    print(f"{'='*60}")

    now = datetime.now()
    end_search = now + timedelta(days=30)  # Look ahead 30 days

    # Get user subjects
    subjects = get_user_subjects_from_db(conn, user_id)
    subject_colour_map = get_subject_colour_map(subjects)
    print(f"[SCHEDULER] User subjects: {[s['subjectName'] for s in subjects]}")

    # Get pending tasks with subject info from JOIN
    tasks = []
    try:
        rows = conn.execute("""
            SELECT t.taskID, t.title, t.description, t.dueDate, t.taskType, t.progress,
                   s.subjectName, s.colourScheme
            FROM tasks t
            LEFT JOIN subjects s ON t.subjectID = s.subjectID
            WHERE t.userID = ?
              AND COALESCE(t.status, 'pending') != 'completed'
              AND t.dueDate IS NOT NULL
            ORDER BY t.dueDate ASC
            LIMIT 30
        """, (user_id,)).fetchall()

        for row in rows:
            due_date = None
            if row['dueDate']:
                try:
                    due_date = datetime.strptime(row['dueDate'], '%Y-%m-%d').date()
                except:
                    try:
                        due_date = datetime.fromisoformat(row['dueDate']).date()
                    except:
                        pass

            if due_date:
                days_until = (due_date - now.date()).days

                # Get subject name and colour from JOIN, or fallback to matching
                subj_name = row['subjectName'] if row['subjectName'] else None
                subj_colour = None

                if subj_name:
                    # Look up colour from our loaded subjects
                    for subj in subjects:
                        if subj['subjectName'].lower() == subj_name.lower():
                            subj_colour = subj['colour']
                            break

                # Fallback: try to match by title if no subject linked
                if not subj_name or not subj_colour:
                    task_title_lower = row['title'].lower()
                    for subj in subjects:
                        if subj['subjectName'].lower() in task_title_lower:
                            subj_name = subj['subjectName']
                            subj_colour = subj['colour']
                            break

                # Final fallback
                if not subj_name:
                    subj_name = 'general'
                if not subj_colour:
                    subj_colour = DEFAULT_COLORS['default']

                tasks.append({
                    'id': row['taskID'],
                    'title': row['title'],
                    'description': row['description'] or '',
                    'due_date': due_date,
                    'due_date_str': str(due_date),
                    'days_until': days_until,
                    'type': row['taskType'] or 'homework',
                    'progress': row['progress'] or 0,
                    'subject': subj_name,
                    'colour': subj_colour
                })

        print(f"[SCHEDULER] Found {len(tasks)} pending tasks")
    except Exception as e:
        print(f"[SCHEDULER] Error loading tasks: {e}")
        import traceback
        traceback.print_exc()

    # Get exams (tasks with type exam/test/quiz)
    exams = []
    for task in tasks:
        if task['type'].lower() in ['exam', 'test', 'quiz']:
            exams.append({
                'id': task['id'],
                'title': task['title'],
                'subject': task['subject'],
                'exam_date': task['due_date'],
                'exam_date_str': task['due_date_str'],
                'days_until': task['days_until'],
                'topics': task['description'],
                'colour': task['colour']
            })

    print(f"[SCHEDULER] Found {len(exams)} upcoming exams")

    # Get existing events
    events = []
    try:
        rows = conn.execute("""
            SELECT eventID, title, startTime, endTime, source
            FROM events
            WHERE userID = ?
              AND isDeleted = 0
              AND startTime >= ?
              AND startTime <= ?
            ORDER BY startTime
        """, (user_id, now.isoformat(), end_search.isoformat())).fetchall()

        for row in rows:
            try:
                start = parse_calendar_dt(row['startTime'])
                end = parse_calendar_dt(row['endTime'])
                if start and end:
                    events.append({
                        'id': row['eventID'],
                        'title': row['title'],
                        'start': start,
                        'end': end,
                        'source': row['source']
                    })
            except:
                continue

        print(f"[SCHEDULER] Found {len(events)} existing events")
    except Exception as e:
        print(f"[SCHEDULER] Error loading events: {e}")

    # Calculate free time windows
    free_slots = calculate_free_time_windows(
        conn, user_id, now, end_search, user_preferences
    )

    print(f"{'='*60}")
    print(f"[SCHEDULER] Data collection complete")
    print(f"{'='*60}\n")

    return {
        'tasks': tasks,
        'exams': exams,
        'events': events,
        'subjects': subjects,
        'subject_colour_map': subject_colour_map,
        'free_slots': free_slots,
        'now': now,
        'end_search': end_search
    }


# ============== GEMINI PROMPT ==============

def build_gemini_schedule_prompt(
    user_prompt: str,
    user_data: Dict,
    user_preferences: Dict,
    options: Dict
) -> str:
    """
    Build a comprehensive prompt for Gemini to generate a study schedule.

    This prompt instructs Gemini to act as an expert HSC study planner
    and incorporates evidence-based study techniques.
    """
    now = user_data['now']
    subjects = user_data['subjects']
    tasks = user_data['tasks']
    exams = user_data['exams']
    free_slots = user_data['free_slots']

    # Build subject list with colours
    subject_list = "\n".join([
        f"- {s['subjectName']} (colour: {s['colour']})"
        for s in subjects
    ])

    # Build tasks summary
    tasks_summary = []
    for t in tasks[:15]:  # Limit to 15 most urgent
        tasks_summary.append({
            'title': t['title'],
            'type': t['type'],
            'subject': t['subject'],
            'due_date': t['due_date_str'],
            'days_until': t['days_until'],
            'priority': 'high' if t['days_until'] <= 3 else 'medium' if t['days_until'] <= 7 else 'normal'
        })

    # Build exams summary
    exams_summary = []
    for e in exams[:10]:  # Limit to 10 upcoming exams
        exams_summary.append({
            'title': e['title'],
            'subject': e['subject'],
            'exam_date': e['exam_date_str'],
            'days_until': e['days_until'],
            'topics': e['topics'][:200] if e['topics'] else ''
        })

    # Build free slots summary (top 20)
    slots_summary = []
    for slot in free_slots[:20]:
        slots_summary.append({
            'date': slot['start'].strftime('%Y-%m-%d'),
            'start_time': slot['start'].strftime('%H:%M'),
            'end_time': slot['end'].strftime('%H:%M'),
            'duration_minutes': slot['duration_minutes'],
            'quality': slot['quality']
        })

    # User preferences
    study_start = user_preferences.get('study_start', 8)
    study_end = user_preferences.get('study_end', 22)
    max_daily = user_preferences.get('max_daily_hours', 4)
    session_duration = user_preferences.get('session_duration', 60)
    break_duration = user_preferences.get('break_duration', 10)
    preferred_techniques = user_preferences.get('study_techniques') or print("[SCHEDULER] No preferred techniques specified by user")
    preferred_techniques_text = ', '.join(preferred_techniques) if preferred_techniques else print("[SCHEDULER] No preferred techniques specified by user")

    # Build the comprehensive prompt
    prompt = f"""You are an expert NSW HSC study planner and learning scientist.

CURRENT TIME: {now.strftime('%Y-%m-%d %H:%M')}

===========================================================
USER'S SUBJECTS (from their saved preferences):
===========================================================
{subject_list or 'No subjects configured'}

===========================================================
PENDING TASKS (from database):
===========================================================
{json.dumps(tasks_summary, indent=2) if tasks_summary else 'None'}

===========================================================
UPCOMING EXAMS:
===========================================================
{json.dumps(exams_summary, indent=2) if exams_summary else 'None'}

===========================================================
AVAILABLE FREE TIME WINDOWS:
===========================================================
{json.dumps(slots_summary, indent=2) if slots_summary else 'No free slots found'}

===========================================================
USER PREFERENCES:
===========================================================
- Preferred study start: {study_start}:00
- Preferred study end: {study_end}:00
- Max daily study: {max_daily} hours
- Session duration: {session_duration} minutes
- Break duration: {break_duration} minutes
- Preferred study techniques: {preferred_techniques_text}

===========================================================
USER PROMPT: "{user_prompt}"

Take any day/exam deadlines that the user has mentioned and subtract 1 day. This is the absolute latest you can schedule a study session for that task/exam. For example, if the user says "I have a math exam on June 20th", you can schedule sessions for that exam up until June 19th, but not on June 20th or later.

===========================================================
EVIDENCE-BASED STUDY TECHNIQUES:
===========================================================

You MUST incorporate these techniques appropriately:

1. SPACED REPETITION
   - Use for content-heavy subjects requiring long-term retention
   - Schedule review sessions at increasing intervals
   - Best for: memorization, language learning, facts

2. ACTIVE RECALL
   - Test yourself rather than re-reading
   - Cover answers and try to recall
   - Best for: exam preparation, concept understanding

3. BLURTING
   - Write down everything you know without looking
   - Then compare with source material
   - Best for: testing understanding after revision

4. STOP-LIGHT METHOD
   - Categorize confidence levels:
     - RED = weak/need more work
     - YELLOW = moderate/confident
     - GREEN = strong/mastered
   - Best for: self-assessment, identifying gaps

5. INTERLEAVING
   - Mix related topics rather than blocking identical tasks
   - Switch between subjects/topics during study
   - Best for: diverse subjects, exam prep

6. RETRIEVAL PRACTICE
   - Practice recalling information without cues
   - Use flashcards, practice questions
   - Best for: any subject with factual content

7. EXAM STYLE QUESTIONS
   - Practice with past papers and exam-format questions
   - Timed practice under exam conditions
   - Best for: near exam dates

8. ERROR ANALYSIS
   - Review mistakes and understand why you got them wrong
   - Create targeted practice for weak areas
   - Best for: after practice tests, before exams

9. WORKED EXAMPLES
   - Study step-by-step solutions
   - Then try similar problems yourself
   - Best for: Maths, Physics, Chemistry

10. PAST PAPER PRACTICE
    - Complete full past exam papers
    - Review under timed conditions
    - Best for: final exam preparation

===========================================================
SCHEDULING REQUIREMENTS:
===========================================================

1. DISTRIBUTE SESSIONS ACROSS TIME
   - Do NOT cluster all sessions on one day
   - Spread sessions from NOW until each deadline
   - Consider days until deadline when determining session frequency

2. USE APPROPRIATE TECHNIQUES
   - If preferred study techniques are selected, prioritize them when they fit the task
   - Use SPACED REPETITION for exams more than 14 days away
   - Use ACTIVE RECALL/RETRIEVAL for subjects with lots of facts
   - Use INTERLEAVING when student has multiple subjects
   - Use ERROR ANALYSIS after any practice tests
   - Use PAST PAPERS for exams within 7 days

3. RESPECT USER CONSTRAINTS
   - Study sessions must be within {study_start}:00 - {study_end}:00
   - Max {max_daily} hours of study per day (including breaks)
   - Sessions should be {session_duration}-{session_duration + 30} minutes
   - Add {break_duration} minute breaks between sessions
   - Use only user selected techniques if they have specified as {preferred_techniques_text}
   - NEVER schedule a session on or after its task due date or exam date
   - For date-only deadlines, the session must END before the deadline date begins

4. MATCH SESSIONS TO AVAILABLE SLOTS
   - Use the provided free time windows
   - Longer sessions (90+ min) prefer weekend afternoons
   - Shorter sessions (45-60 min) can fit in weekday evenings

5. IMPORTANT: EVENT NAMING
   - NEVER use generic names like "Deadline: Thursday"
   - ALWAYS use meaningful, descriptive titles like:
     - "Chemistry Module 8 Revision"
     - "Maths Ext 2 Past Paper Practice"
     - "English Essay Planning"
     - "Physics Wave Definitions Flashcards"
     - "Biology Cell Structure Active Recall"
   - Titles should indicate WHAT to study and HOW

6. COLOUR CODING
   - Use the subject colour from the user's saved subjects
   - The colour is already provided in the subject list

NON-NEGOTIABLE RULE:
Every study session MUST occur before the assessment deadline.
Do not create sessions on or after the deadline.

===========================================================
OUTPUT FORMAT (STRICT JSON):
===========================================================

Return ONLY valid JSON with this structure (NO markdown, NO explanations):

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
Use 24-hour HH:MM strings for suggested_start_time (for example "14:30", not "2:30 PM").
"""

    return prompt


# ============== MAIN SCHEDULING FUNCTION ==============

def generate_smart_schedule_with_gemini(
    user_prompt: str,
    user_data: Dict,
    user_preferences: dict,
    options: dict
) -> dict:
    """
    Use Gemini to intelligently analyze user needs and generate a study schedule.

    This is the main entry point for schedule generation.

    Args:
        user_prompt: Natural language description from user
        user_data: Dict with tasks, exams, events, subjects, free_slots from collect_user_data()
        user_preferences: User preferences (study hours, etc.)
        options: Scheduling options

    Returns:
        dict with 'sessions', 'summary', and 'reasoning'
    """
    print(f"\n{'='*60}")
    print(f"[GEMINI_SCHEDULE] Starting Gemini-powered schedule generation")
    print(f"{'='*60}")

    ask_gemini_json = _get_gemini_client()
    if not ask_gemini_json:
        print(f"[GEMINI_SCHEDULE] Gemini client not available")
        return {'error': 'Gemini not available', 'sessions': []}

    # Build the comprehensive prompt
    prompt = build_gemini_schedule_prompt(
        user_prompt,
        user_data,
        user_preferences,
        options
    )

    print(f"[GEMINI_SCHEDULE] Prompt built, sending to Gemini...")
    print(f"[GEMINI_SCHEDULE] Prompt length: {len(prompt)} chars")

    try:
        result = ask_gemini_json(prompt, temperature=0.3, max_output_tokens=6000)

        print(f"[GEMINI_SCHEDULE] Received response from Gemini")
        print(f"[GEMINI_SCHEDULE] Response type: {type(result)}")

        if isinstance(result, (dict, list)):
            sessions_data, reasoning, techniques = normalize_gemini_schedule_result(result)

            print(f"[GEMINI_SCHEDULE] Parsed {len(sessions_data)} study sessions")
            print(f"[GEMINI_SCHEDULE] Techniques used: {techniques}")

            # Process sessions and allocate to free slots
            processed_sessions = allocate_sessions_to_slots(
                sessions_data,
                user_data,
                user_preferences,
                options
            )

            return {
                'sessions': processed_sessions,
                'summary': get_schedule_summary(processed_sessions),
                'reasoning': reasoning,
                'techniques_used': techniques
            }
        print(f"[GEMINI_SCHEDULE] Invalid response type: {type(result)}")
        return {'error': 'Invalid Gemini response', 'sessions': []}

    except Exception as e:
        print(f"[GEMINI_SCHEDULE] Error: {e}")
        import traceback
        traceback.print_exc()
        return {'error': str(e), 'sessions': []}


def allocate_sessions_to_slots(
    sessions_data: List[Dict],
    user_data: Dict,
    user_preferences: Dict,
    options: Dict
) -> List[Dict]:
    """
    Allocate generated study sessions to available free slots.

    FIXES:
    1. Removes undefined variables (start_dt, deadline_dt) that were causing
       allocation failures and resulting in 0 sessions.
    2. Enforces strict deadline compliance.
    3. Allocates sessions chronologically rather than randomly.
    4. Allows multiple sessions inside large free windows.
    5. Prevents overlap.
    """

    print(f"\n{'=' * 60}")
    print(f"[ALLOCATOR] Allocating {len(sessions_data)} sessions to free slots")
    print(f"{'=' * 60}")

    free_slots = sorted(
        user_data.get("free_slots", []),
        key=lambda s: s["start"]
    )

    subjects = user_data.get("subjects", [])
    subject_colour_map = user_data.get("subject_colour_map", {})

    # Remaining availability inside each slot
    working_slots = [
        {
            "start": slot["start"],
            "end": slot["end"],
            "duration_minutes": slot["duration_minutes"],
            "quality": slot.get("quality", "good")
        }
        for slot in free_slots
    ]

    allocated_sessions = []

    # Sort sessions by urgency first
    def session_priority(session):
        deadline = deadline_datetime_for_session(session, user_data)
        if deadline:
            return deadline
        return datetime.max

    sessions_data = sorted(sessions_data, key=session_priority)

    for session in sessions_data:
        subject_name = session.get("subject", "General")
        title = session.get("title", "Study Session")

        duration = coerce_minutes(
            session.get("duration_minutes", 60),
            60
        )

        strategy = session.get("strategy", "Study")
        reasoning = session.get("reasoning", "")

        deadline_dt = deadline_datetime_for_session(
            session,
            user_data
        )

        colour = subject_colour_map.get(
            subject_name.lower(),
            DEFAULT_COLORS["default"]
        )

        found_slot = None
        scheduled_start = None
        scheduled_end = None

        suggested_date = normalize_date_text(
            session.get("suggested_date")
        )

        # --------------------------------------------------
        # PASS 1: honour Gemini's suggested date if possible
        # --------------------------------------------------
        if suggested_date:
            for slot in working_slots:

                if slot["start"].strftime("%Y-%m-%d") != suggested_date:
                    continue

                if slot["duration_minutes"] < duration:
                    continue

                candidate_start = slot["start"]
                candidate_end = candidate_start + timedelta(
                    minutes=duration
                )

                if deadline_dt and candidate_end >= deadline_dt:
                    continue

                found_slot = slot
                scheduled_start = candidate_start
                scheduled_end = candidate_end
                break

        # --------------------------------------------------
        # PASS 2: earliest valid slot (chronological order)
        # --------------------------------------------------
        if not found_slot:
            for slot in working_slots:

                if slot["duration_minutes"] < duration:
                    continue

                candidate_start = slot["start"]
                candidate_end = candidate_start + timedelta(
                    minutes=duration
                )

                if deadline_dt and candidate_end >= deadline_dt:
                    continue

                found_slot = slot
                scheduled_start = candidate_start
                scheduled_end = candidate_end
                break

        if not found_slot:
            print(
                f"[ALLOCATOR] No valid slot before deadline for: {title}"
            )
            continue

        # --------------------------------------------------
        # Consume only the used portion of the free slot
        # --------------------------------------------------
        found_slot["start"] = scheduled_end
        found_slot["duration_minutes"] = int(
            (found_slot["end"] - found_slot["start"]).total_seconds()
            / 60
        )

        description = f"Strategy: {strategy}\n"

        if reasoning:
            description += f"Reason: {reasoning}\n"

        task_id = session.get("task_id")
        exam_id = session.get("exam_id")

        if task_id:
            description += f"Related Task ID: {task_id}"

        elif exam_id:
            description += f"Related Exam ID: {exam_id}"

        allocated_sessions.append({
            "title": title,
            "subject": subject_name,
            "start": scheduled_start.isoformat(),
            "end": scheduled_end.isoformat(),
            "duration_minutes": duration,
            "priority": session.get("priority", "normal"),
            "strategy": strategy,
            "reasoning": reasoning,
            "description": description,
            "colour": colour,
            "type": "study",
            "task_id": task_id,
            "exam_id": exam_id
        })

        print(
            f"[ALLOCATOR] Allocated: {title} -> "
            f"{scheduled_start.strftime('%Y-%m-%d %H:%M')}"
        )

    allocated_sessions.sort(
        key=lambda s: datetime.fromisoformat(s["start"])
    )

    print(
        f"[ALLOCATOR] Successfully allocated "
        f"{len(allocated_sessions)} sessions"
    )

    return allocated_sessions


def time_to_minutes(time_str: str) -> int:
    """Convert HH:MM to minutes since midnight."""
    try:
        text = str(time_str or '').strip().lower()
        text = re.sub(r'\s+', '', text)
        ampm = None
        if text.endswith('am') or text.endswith('pm'):
            ampm = text[-2:]
            text = text[:-2]
        if ':' in text:
            parts = text.split(':')
            hour = int(parts[0])
            minute = int(parts[1])
        else:
            hour = int(text)
            minute = 0
        if ampm == 'pm' and hour != 12:
            hour += 12
        elif ampm == 'am' and hour == 12:
            hour = 0
        return hour * 60 + minute
    except Exception:
        return 0


def coerce_minutes(value, default=60) -> int:
    """Accept 60, '60', '60 minutes', '1.5 hours'."""
    if isinstance(value, (int, float)):
        return max(15, min(240, int(value)))
    text = str(value or '').lower()
    nums = re.findall(r'\d+(?:\.\d+)?', text)
    if not nums:
        return default
    number = float(nums[0])
    if 'hour' in text or 'hr' in text:
        number *= 60
    return max(15, min(240, int(number)))


def normalize_date_text(value) -> Optional[str]:
    """Normalize Gemini date variants to YYYY-MM-DD."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value.strftime('%Y-%m-%d')
    if isinstance(value, date):
        return value.strftime('%Y-%m-%d')
    text = str(value).strip()
    try:
        return datetime.fromisoformat(text.replace('Z', '+00:00')).strftime('%Y-%m-%d')
    except Exception:
        pass
    match = re.search(r'\d{4}-\d{2}-\d{2}', text)
    if match:
        return match.group(0)
    return text


def normalize_gemini_schedule_result(result) -> tuple:
    """Accept common Gemini JSON shapes instead of only {'study_sessions': [...]}."""
    if isinstance(result, list):
        return result, '', []
    for key in ('study_sessions', 'sessions', 'schedule', 'events', 'study_plan'):
        value = result.get(key)
        if isinstance(value, list):
            return value, result.get('reasoning', ''), result.get('techniques_used', [])
    nested = result.get('schedule')
    if isinstance(nested, dict):
        for key in ('study_sessions', 'sessions', 'events'):
            value = nested.get(key)
            if isinstance(value, list):
                return value, result.get('reasoning') or nested.get('reasoning', ''), result.get('techniques_used') or nested.get('techniques_used', [])
    return [], result.get('reasoning', ''), result.get('techniques_used', [])


def parse_deadline_date(value) -> Optional[date]:
    """Parse a date/datetime-like value into a date."""
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return datetime.fromisoformat(str(value)).date()
    except Exception:
        try:
            return datetime.strptime(str(value), '%Y-%m-%d').date()
        except Exception:
            return None


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

    return None


def slot_before_deadline(slot: Dict, duration_minutes: int, deadline_dt: Optional[datetime]) -> bool:
    if not deadline_dt:
        return True
    return slot['start'] + timedelta(minutes=duration_minutes) < deadline_dt


# ============== HELPER FUNCTIONS ==============

def get_schedule_summary(sessions: list) -> dict:
    """Generate a summary of the schedule."""
    if not sessions:
        return {'total_sessions': 0, 'total_hours': 0, 'by_subject': {}, 'by_type': {}}

    total_minutes = 0
    by_subject = defaultdict(int)
    by_type = defaultdict(int)
    by_strategy = defaultdict(int)

    for session in sessions:
        if session.get('type') == 'break':
            continue

        start = session.get('start')
        end = session.get('end')

        if start and end:
            try:
                start_dt = datetime.fromisoformat(start) if isinstance(start, str) else start
                end_dt = datetime.fromisoformat(end) if isinstance(end, str) else end
                duration = (end_dt - start_dt).total_seconds() / 60
                total_minutes += duration
            except Exception:
                pass

        subject = session.get('subject', 'general')
        by_subject[subject] += 1

        session_type = session.get('type', 'study')
        by_type[session_type] += 1

        strategy = session.get('strategy', 'Study')
        by_strategy[strategy] += 1

    return {
        'total_sessions': len([s for s in sessions if s.get('type') != 'break']),
        'total_hours': round(total_minutes / 60, 1),
        'by_subject': dict(by_subject),
        'by_type': dict(by_type),
        'by_strategy': dict(by_strategy),
        'date_range': _get_date_range(sessions)
    }


def _get_date_range(sessions: list) -> dict:
    """Get the date range of the schedule."""
    if not sessions:
        return None

    dates = []
    for session in sessions:
        start = session.get('start')
        if start:
            try:
                dt = datetime.fromisoformat(start) if isinstance(start, str) else start
                dates.append(dt.date())
            except Exception:
                pass

    if dates:
        return {'start': min(dates), 'end': max(dates)}
    return None


def parse_calendar_dt(dt_str: str) -> datetime:
    """Parse datetime string from database."""
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str.replace('Z', '+00:00').replace(' ', 'T'))
    except Exception:
        try:
            return datetime.strptime(dt_str, '%Y-%m-%d %H:%M:%S')
        except Exception:
            try:
                return datetime.strptime(dt_str, '%Y-%m-%dT%H:%M:%S')
            except Exception:
                return None


# ============== LEGACY FUNCTIONS (for backwards compatibility) ==============

def generate_smart_schedule_with_gemini_legacy(
    user_prompt: str,
    db_tasks: list,
    db_exams: list,
    user_preferences: dict,
    options: dict
) -> dict:
    """
    Legacy function for backwards compatibility.
    Wraps the new function with old-style parameters.
    """
    # This is kept for compatibility but should be replaced with the new approach
    user_data = {
        'tasks': db_tasks,
        'exams': db_exams,
        'subjects': [],
        'free_slots': [],
        'now': datetime.now()
    }
    return generate_smart_schedule_with_gemini(user_prompt, user_data, user_preferences, options)


# ============== NLP PARSING (kept for other uses) ==============

SUBJECTS = {
    'maths': ['maths', 'math', 'mathematics', 'algebra', 'calculus', 'geometry'],
    'english': ['english', 'literature', 'essay', 'reading', '写作'],
    'physics': ['physics', 'phys', 'forces', 'waves', 'thermodynamics'],
    'chemistry': ['chemistry', 'chem', 'organic', 'reactions', 'periodic'],
    'biology': ['biology', 'bio', 'cells', 'genetics', 'evolution'],
    'economics': ['economics', 'econ', 'market', 'micro', 'macro'],
    'history': ['history', 'ancient', 'modern', 'hsc'],
    'geography': ['geography', 'geo', 'environmental', 'urban'],
    'legal': ['legal', 'law', 'legal studies'],
    'business': ['business', 'business studies', 'marketing'],
    'languages': ['language', 'french', 'german', 'japanese', 'chinese', 'spanish'],
    'ict': ['ict', 'computing', 'software', 'programming', 'code'],
}


def parse_freeform_text(text: str) -> dict:
    """Parse freeform text input to extract scheduling information."""
    if not text:
        return {'subjects': [], 'dates': [], 'durations': [], 'priorities': [], 'tasks': []}

    text = text.lower()
    result = {
        'subjects': extract_subjects(text),
        'dates': extract_dates(text),
        'durations': extract_durations(text),
        'priorities': extract_priorities(text),
        'tasks': extract_tasks(text)
    }

    return result


def extract_subjects(text: str) -> list:
    """Extract subjects from text using keyword matching."""
    found = []
    text_lower = text.lower()

    for subject, keywords in SUBJECTS.items():
        for keyword in keywords:
            if keyword in text_lower:
                if subject not in found:
                    found.append(subject)
                break

    return found


def extract_dates(text: str) -> list:
    """Extract dates from text with contextual information."""
    dates = []
    now = datetime.now()
    text_lower = text.lower()

    if 'tomorrow' in text_lower:
        tomorrow = now + timedelta(days=1)
        dates.append({
            'date': tomorrow.date(),
            'context': 'tomorrow',
            'urgency': 8
        })

    if 'today' in text_lower:
        dates.append({
            'date': now.date(),
            'context': 'today',
            'urgency': 10
        })

    day_patterns = [
        (r'\bnext\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b', 7, True),
        (r'\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b', 0, False)
    ]

    for pattern, offset_base, is_next in day_patterns:
        matches = re.findall(pattern, text_lower)
        for match in matches:
            target_day = DAYS_OF_WEEK[match]
            current_day = now.weekday()

            if is_next:
                days_until = (target_day - current_day + 7) % 7
                if days_until == 0:
                    days_until = 7
            else:
                days_until = (target_day - current_day + 7) % 7

            target_date = (now + timedelta(days=days_until)).date()

            existing = False
            for d in dates:
                if d['date'] == target_date:
                    existing = True
                    break

            if not existing:
                days_diff = (target_date - now.date()).days
                urgency = max(1, 10 - days_diff)
                dates.append({
                    'date': target_date,
                    'context': match,
                    'urgency': urgency
                })

    return dates


def extract_durations(text: str) -> list:
    """Extract study durations from text."""
    durations = []
    text_lower = text.lower()

    patterns = [
        (r'(\d+)\s*(?:hour|hr)s?\s*(?:and\s*(\d+)\s*(?:minute|min))?', 60),
        (r'(\d+)\s*(?:hour|hr)s?', 60),
        (r'(\d+)\s*(?:minute|min)\s*(?:study|session)?', 1),
        (r'half\s*an?\s*hour', 30),
        (r'one\s+hour', 60),
        (r'two\s+hours', 120),
    ]

    for pattern, multiplier in patterns:
        matches = re.findall(pattern, text_lower)
        for match in matches:
            if isinstance(match, tuple):
                hours = int(match[0]) if match[0] else 0
                mins = int(match[1]) if len(match) > 1 and match[1] else 0
                total_mins = hours * multiplier + mins
            else:
                total_mins = int(match) * multiplier

            if total_mins > 0 and total_mins <= 480:
                durations.append({'minutes': total_mins, 'context': 'explicit'})

    return durations


def extract_priorities(text: str) -> list:
    """Extract priority indicators from text."""
    priorities = []
    text_lower = text.lower()

    priority_keywords = {
        'urgent': 10, 'asap': 10, 'immediately': 10, 'critical': 9,
        'important': 7, 'soon': 6, 'priority': 7,
        'cramming': 8, 'last minute': 7, 'memorize': 5,
        'revision': 4, 'review': 3, 'practice': 3, 'finish': 5,
        'complete': 4, 'submit': 6, 'due': 7
    }

    for keyword, weight in priority_keywords.items():
        if keyword in text_lower:
            priorities.append({'keyword': keyword, 'weight': weight})

    return sorted(priorities, key=lambda x: x['weight'], reverse=True)


def extract_tasks(text: str) -> list:
    """Extract tasks with deadlines from text."""
    tasks = []
    text_lower = text.lower()

    task_keywords = ['exam', 'test', 'quiz', 'assessment', 'assignment', 'essay', 'report', 'project', 'homework', 'paper', 'trial']

    for keyword in task_keywords:
        if keyword in text_lower:
            for subject, keywords in SUBJECTS.items():
                for kw in keywords:
                    pattern = rf'{kw}\s+(?:{"|".join(task_keywords)})'
                    if re.search(pattern, text_lower):
                        tasks.append({
                            'type': keyword,
                            'subject': subject,
                            'context': text_lower
                        })
                        break

    return tasks


# ============== PRIORITY SCORING (kept for compatibility) ==============

def calculate_priority_score(item: dict, user_preferences: dict = None) -> float:
    """Calculate priority score for a scheduling item."""
    score = 0
    user_preferences = user_preferences or {}

    if 'due_date' in item:
        due_date = item['due_date']

        if isinstance(due_date, str):
            try:
                due_date = datetime.fromisoformat(due_date).date()
            except:
                try:
                    due_date = datetime.strptime(due_date, '%Y-%m-%d').date()
                except:
                    due_date = None

        if due_date is not None:
            try:
                days_until = (due_date - datetime.now().date()).days
                if days_until <= 0:
                    score += 50
                elif days_until <= 1:
                    score += 40
                elif days_until <= 3:
                    score += 30
                elif days_until <= 7:
                    score += 20
                elif days_until <= 14:
                    score += 10
                else:
                    score += max(0, 15 - days_until)
            except:
                pass

    task_type_weights = {
        'exam': 25, 'test': 22, 'quiz': 20,
        'assignment': 15, 'essay': 15, 'project': 12,
        'homework': 10, 'revision': 8, 'practice': 5
    }
    task_type = item.get('type', '').lower()
    score += task_type_weights.get(task_type, 10)

    priority_subjects = user_preferences.get('priority_subjects', [])
    if 'subject' in item and item['subject'] in priority_subjects:
        score += 15

    if 'urgency' in item:
        score += item['urgency'] * 2

    if 'estimated_hours' in item:
        score += min(10, item['estimated_hours'] * 2)

    return score
