# Dusty AI

## Overview

Dusty AI is an AI-powered study assistant developed as a Year 12 Software Engineering Major Project. The application combines intelligent scheduling, personalised study planning, task management, progress tracking, and AI-assisted learning tools to help students organise and improve their study habits.

Dusty AI allows users to:

* Create and manage study schedules
* Generate personalised study plans using AI (Gemini)
* Track assignments and deadlines
* Manage subjects and study preferences
* Receive AI-generated study recommendations
* View progress analytics and performance insights
* Customise study techniques and scheduling preferences
* Study using flashcards with spaced repetition
* Use an AI-powered chat for study assistance
* Upload and manage study resources
* Sync with Google Calendar
* Customise the study timer with ambience

---

# System Requirements

Before running the application, ensure the following software is installed:

### Required Software

* Git
* Python 3.11 or newer
* Visual Studio Code (optional for running and debugging locally)
* Google Chrome, Microsoft Edge, Firefox, or another modern browser
* Google API credentials (for Calendar sync) - see setup below

### Recommended Hardware

* 4GB RAM minimum
* Internet connection (required for AI functionality)

---

# End User License Agreement (EULA)
Please see to the user agreement before proceeding: [EULA.md](https://github.com/overism/12SE_YatharthJain_MajorProject/blob/main/EULA.md)

# Installation

## 1. Clone the Repository

Open Command Prompt, PowerShell, or Terminal and run:

```bash
git clone https://github.com/overism/12SE_YatharthJain_MajorProject
cd 12SE_YatharthJain_MajorProject
```

Alternatively, download the ZIP file and extract it.

---

## 2. Create a Virtual Environment

### Windows

```bash
python -m venv .venv
```

### macOS / Linux

```bash
python3 -m venv .venv
```

---

## 3. Activate the Virtual Environment

### Windows

```bash
.venv\Scripts\activate
```

### macOS / Linux

```bash
source .venv/bin/activate
```

You should now see:

```text
(.venv) #at the beginning of your terminal prompt.
```

---

## 4. Install Required Packages (estimated install time: 5-10 minutes)

Install all project dependencies:

Run the following command:
```text
cd WebServer\Dusty_PWA
```

Then:
```bash
pip install -r requirements.txt
```

If a requirements file is not provided, install the required packages manually:

```bash
pip install flask
pip install flask-cors
pip install flask-session
pip install werkzeug
pip install requests
pip install google-generativeai
```

---

## Missing Dependencies

If Python reports:

```text
ModuleNotFoundError
```

install the missing package:

```bash
pip install package-name
```

or reinstall all requirements:

```bash
pip install -r requirements.txt
```

---

## 5. Environment Variables Setup
Locate portfolio and follow insturctions for environment variable and database set up 

Create a `.env` file in the `WebServer/Dusty_PWA` directory with the following variables:

```
# Flask Secret Key (generate a random string for production)
SECRET_KEY=your_secret_key_here

# Google Gemini API Key (for AI scheduling and chat)
GEMINI_API_KEY=your_gemini_api_key

# Google OAuth (for Calendar sync) - see Google Calendar Setup below
GOOGLE_REDIRECT_URI=http://localhost:5000/oauth2callback

```
It is preferred to use the API key and .env variables attached in the portfolio.

---

# Running the Application

Navigate to the application directory:

```bash
cd WebServer/Dusty_PWA
```

Start the Flask server:

```bash
python app.py
```

If successful, you should see output similar to:

```text
* Running on http://127.0.0.1:5000
```

---

# Accessing Dusty AI

Open a web browser and visit:

```text
http://127.0.0.1:5000
```

or

```text
http://localhost:5000
```

The login page should load automatically.

---

# Creating an Account

1. Open the signup page.
2. Enter:
   * Username
   * Email Address
   * Password
3. Complete onboarding preferences.
4. Log in to access the dashboard.

---

# Features

## 1. Dashboard

The home dashboard provides:

* Quick overview of upcoming tasks
* Days remaining countdown
* Subject-wise task distribution
* Quick access to all features
* Progress monitoring widgets

---

## 2. Study Scheduler

The intelligent study scheduler is the core feature of Dusty AI:

* **AI-generated study plans** - Uses Google Gemini to create personalized study schedules
* **Deadline-aware scheduling** - Automatically schedules study sessions before due dates
* **User-selected study techniques** - Choose from evidence-based techniques:
  - Spaced Repetition
  - Active Recall
  - Blurting
  - Stop-Light Method
  - Interleaving
  - Retrieval Practice
  - Exam Style Questions
  - Error Analysis
  - Worked Examples
  - Past Paper Practice
* **Time management optimisation** - Respects study hours, sleep hours, and school hours
* **Smart slot allocation** - Finds available time windows in your calendar

### How to Generate a Schedule

1. Go to the Calendar page
2. Click "Generate Schedule" or use the smart scheduler
3. Enter your requirements in natural language
4. AI creates study sessions mapped to available time slots

---

## 3. Subject Management

* Add limited HSC subjects with custom colours
* Colour options: orange, blue, green, red, purple, yellow, brown, amber, teal, pink
* Set priority subjects for focused study
* Customise study preferences per subject

---

## 4. Task Management

* Create tasks with title, subject, due date, and type
* Task types: Homework, Exam, Project, Study, Assignment, Other
* Track progress (0-100%)
* View days remaining until due
* Link tasks to calendar events automatically

---

## 5. AI Assistance (Chat)

The AI chat provides:

* Gemini-powered study support
* Retrieval-Augmented Generation (RAG) from your uploaded resources
* Subject-aware responses
* Study help, explanation, and practice questions

### Using the Chat

1. Go to the Chat page
2. Select a subject (optional)
3. Ask questions about your study material
4. AI references your uploaded resources when answering

---

## 6. Flashcards

Create and study flashcards:

* Create decks organized by subject and module
* Add cards with question, answer, and hint
* Study sessions track results (knew/unsure/missed)
* Review performance analytics

---

## 7. Study Timer

Customisable Pomodoro-style timer:

* Set custom study and break durations
* **Ambience customization**:
  - Custom background images/videos
  - Custom ambient sounds
  - Multiple ambience presets
* Audio notifications for session end
* Progress tracking per session

---

## 8. Progress Tracking

* View study analytics and statistics
* Track completed sessions
* Monitor task completion rates
* Flashcard study results
* Timer session history

---

## 9. Resources Management

* Upload study materials (PDF, DOCX, PPTX, TXT, images)
* Organise resources by subject
* AI uses these resources in chat responses (RAG)
* File browser with directory structure

---

## 10. Google Calendar Integration

Sync your study schedule with Google Calendar:

1. Go to Calendar page
2. Click "Connect Google Calendar"
3. Authorize the application
4. Events sync automatically:
   - Created events appear in Google Calendar
   - Google Calendar events appear in Dusty AI

---

## 11. Profile & Settings

* Update username and email
* Upload profile avatar
* Set bio
* Change password
* Delete account
* Theme customisation (light/dark)
* Export/manage data

---

# Technology Stack

### Backend
* **Python** - Primary programming language
* **Flask** - Web framework
* **SQLite** - Local database
* **Google Gemini API** - AI for scheduling and chat
* **Google Calendar API** - Calendar sync
* **Chromadb** - Vector database for RAG

### Frontend
* **HTML5** - Structure
* **CSS3** - Styling with CustomTkinter-inspired design
* **JavaScript** - Interactivity
* **FullCalendar** - Calendar visualization
* **PWA** - Progressive Web App capabilities

---

# Author

**Yatharth Jain**

Year 12 Software Engineering Major Project

Girraween High School

2026

---

# Acknowledgements

* Python
* Flask
* SQLite
* Google Gemini API
* Google Calendar API
* ChromaDB
* HTML, CSS, and JavaScript
* FullCalendar

---

# License

This project was developed for educational purposes as part of the NSW Stage 6 Software Engineering course.

---
