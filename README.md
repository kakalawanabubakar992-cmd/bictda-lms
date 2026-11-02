# BICTDA LMS - Internship & Digital Skills Portal

Internship and Learning Management System for the **Borno State Information and
Communication Technology Development Agency (BICTDA)**, built for SIWES students and
NYSC corps members.

## Features
- Two sign-in portals: Interns (sign in with email, Intern ID or phone) and Facilitators (Facilitator ID)
- SIWES and NYSC programmes with auto-generated IDs (`BICTDA-SIWES-001`, `BICTDA-NYSC-001`)
- One 6-month track of 4 courses for SIWES and NYSC, taken in order. The next course unlocks only when the final score is **50% or more**
- Attendance with punctuality credit: Punctual 100%, Late 50%, Absent 0%
- Assignments: facilitators post and grade them, interns submit them
- Chart.js dashboards, works on phones and can be installed as an app (PWA)

## Course track (same for every SIWES and NYSC intern, 6 months)
| # | Course | Expected duration |
|---|---|---|
| 1 | Web Development | 1 month |
| 2 | Data Science & Python | 2 months |
| 3 | Machine Learning | 1 month |
| 4 | Cybersecurity | 2 months |

Courses are edited in one place: `COURSES` in `seed.py`. The pass mark is `PASS_MARK` in `models.py`.

## Tech stack
Python 3.12, Flask, Flask-Login, Flask-WTF, Flask-SQLAlchemy, SQLite (local) / PostgreSQL on Neon (live),
Tailwind CSS, Chart.js, Gunicorn, Render.

## Run locally
```bash
python -m venv venv
# Windows: venv\Scripts\activate     macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
copy .env.example .env               # macOS/Linux: cp .env.example .env
python seed.py                       # creates bictda_lms.db with demo data
```

## Demo accounts
| Role | Login ID | Password |
|---|---|---|
| Facilitator (Data Science, Machine Learning) | BICTDA-FAC-001 | Facilitator@123 |
| Facilitator (Web Development, Cybersecurity) | BICTDA-FAC-002 | Facilitator@123 |
| SIWES Intern (on Course 2) | BICTDA-SIWES-001 | Intern@123 |
| SIWES Intern (scored 45%, retake) | BICTDA-SIWES-002 | Intern@123 |
| SIWES Intern | BICTDA-SIWES-003 | Intern@123 |
| NYSC Intern | BICTDA-NYSC-001 | Intern@123 |
| NYSC Intern | BICTDA-NYSC-002 | Intern@123 |

Final-year Software Engineering project.
