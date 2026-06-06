# Dusty AI

## Overview

Dusty AI is an AI-powered study assistant developed as a Year 12 Software Engineering Major Project. The application combines intelligent scheduling, personalised study planning, task management, progress tracking, and AI-assisted learning tools to help students organise and improve their study habits.

Dusty AI allows users to:

* Create and manage study schedules
* Generate personalised study plans using AI
* Track assignments and deadlines
* Manage subjects and study preferences
* Receive AI-generated study recommendations
* View progress analytics and performance insights
* Customise study techniques and scheduling preferences

---

# System Requirements

Before running the application, ensure the following software is installed:

### Required Software

* Python 3.11 or newer
* Git
* Google Chrome, Microsoft Edge, Firefox, or another modern browser

### Recommended Hardware

* 4GB RAM minimum
* Internet connection (required for AI functionality)

---

# Installation

## 1. Clone the Repository

Open Command Prompt, PowerShell, or Terminal and run:

```bash
git clone <repository-url>
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
(.venv)
```

at the beginning of your terminal prompt.

---

## 4. Install Required Packages

Install all project dependencies:

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

# Features

### Study Scheduler

* AI-generated study plans
* Deadline-aware scheduling
* User-selected study techniques
* Time management optimisation

### Subject Management

* Subject colour customisation
* Priority subject allocation
* Personalised study preferences

### AI Assistance

* Gemini-powered study support
* Intelligent recommendations
* Dynamic schedule generation

### Dashboard

* Progress monitoring
* Task tracking
* Schedule visualisation

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
* HTML, CSS, and JavaScript
* CustomTkinter (where applicable)

---

# License

This project was developed for educational purposes as part of the NSW Stage 6 Software Engineering course.
