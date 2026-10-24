# JARVIS

A personal assistant project, starting with Gmail exports and a local SQLite database.

## React homepage

The `frontend/` directory contains a React + Vite homepage with the JARVIS logo
centered on a black background. It requires Node.js 20.19+ (20.x) or 22.12+.

```bash
cd frontend
npm install
npm run dev
```

Open the local URL printed by Vite. To create a production build, run
`npm run build`; the output is saved in `frontend/dist/`. Use `npm run preview`
to preview that build locally.

## Project layout

```text
scripts/
  fetch_gmail.py       # Download Gmail messages
  import_gmail.py      # Decode and load raw Gmail messages into SQLite
  fetch_calendar.py    # Download upcoming Calendar events
  import_calendar.py   # Load Calendar events into SQLite
examples/
  llm_example.py       # Standalone model API example
  summarize_emails.py  # Summarize selected database emails
sql/
  list_emails.sql      # Query the Gmail table
data/                 # Local files; excluded from Git
  gmail/
    raw_emails.json
    cleaned_emails.json
    raw_calendars.json # Existing scripts currently reference this path
  exports/
    emails.csv
    email_summary.csv
  samples/
    sample_emails.json
  linkedin/           # LinkedIn CSV exports
  jarvis.db
secrets/              # Local Gmail credentials; excluded from Git
  gmail_credentials.json
  gmail_token.json
assets/
  jarvis_logo.png
  jarvis_logo_transparent.png
```

Python filenames use lowercase words separated by underscores and describe each script's action.

## Run scripts

From the project root, activate the existing virtual environment:

```bash
source .venv/bin/activate
```

Fetch Gmail messages using your existing Gmail authorization:

```bash
python scripts/fetch_gmail.py
```

Import the raw export into SQLite:

```bash
python scripts/import_gmail.py
```

The importer currently drops and rebuilds the `gmail` table each time. Manual changes to that table are overwritten.

Run the saved query:

```bash
sqlite3 -header -column data/jarvis.db ".read sql/list_emails.sql"
```

Export the Gmail table to CSV:

```bash
sqlite3 -header -csv data/jarvis.db "SELECT * FROM gmail;" > data/exports/emails.csv
```

The Gmail scripts resolve data and credential paths relative to the project location, so those paths also work when the scripts are launched from another directory.

The scripts in `examples/` make API requests when run and expect `OPENAI_API_KEY` in the environment. They do not load `.env` themselves.

## Crowdmark scores

Keep Chrome open with the Playwright extension installed in your intended profile.
Set `PLAYWRIGHT_MCP_EXTENSION_TOKEN` in the root `.env` file, then run:

```bash
python "automations/crowdmark.py"
```

The automation uses the existing browser session, or
opens the Waterloo LEARN sign-in flow if necessary. Complete university sign-in
when prompted; it does not enter passwords or approve MFA.

The script visits every course linked on the course list and exports assessment
titles, statuses, displayed scores, numeric percentages when available, and
source URLs to `data/crowdmark/scores.json`. Each run replaces this export.
Missing scores remain `null`, while an actual `0%` is stored as zero. The report
records per-course results and checks assessment counts against the course list
when those counts are displayed. Partial runs are flagged rather than reported
as complete. This workflow does not call a language model or change grades.

It requires Node.js/`npx` and the Python packages `mcp` and `python-dotenv` in your
virtual environment.

## Fall 2026 course outlines

With Chrome open and the same extension token configured, run:

```bash
python automations/course_outlines.py
```

The script selects the View links only within the enrolled Fall 2026 course
table. It switches to each opened outline tab and exports its Tentative Class
Plan section to `data/course_outlines/fall_2026_class_plans.json`.

Each table keeps its original column names and row values. `original_cells`
preserves every row, including the header, with cell types and row/column spans.
Original table HTML, section HTML, and surrounding notes are also saved. Dates,
topics, and assessments are not normalized. Missing sections or extraction
failures are flagged per course; rerunning replaces the JSON export.
