# JARVIS

A personal assistant project, starting with Gmail exports and a local SQLite database.

## Automatic Gmail sync on macOS

`launchd/com.jarvis.gmail-sync.plist` runs Gmail sync at login/load and every
five minutes while your Mac is awake and you are logged in. It uses the project's
virtual environment and writes directly to SQLite. The paths in this file are
specific to `/Users/opthukral/JARVIS-1`; update them if the checkout moves.

Authorize Gmail manually before enabling the agent:

```bash
.venv/bin/python scripts/fetch_gmail.py
mkdir -p data/logs "$HOME/Library/LaunchAgents"
cp launchd/com.jarvis.gmail-sync.plist "$HOME/Library/LaunchAgents/"
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.jarvis.gmail-sync.plist"
```

The scheduled command uses `--non-interactive`: it refreshes the saved token,
but reports an error instead of opening sign-in if authorization is required.
Logs are in ignored `data/logs/gmail-sync.log` and
`data/logs/gmail-sync.error.log`. The existing fetcher checks one page of inbox
messages each run; incremental history synchronization is not implemented yet.

Check status or run the job immediately:

```bash
launchctl print "gui/$(id -u)/com.jarvis.gmail-sync"
launchctl kickstart "gui/$(id -u)/com.jarvis.gmail-sync"
```

To disable it now and prevent it starting at future logins:

```bash
launchctl bootout "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.jarvis.gmail-sync.plist"
rm "$HOME/Library/LaunchAgents/com.jarvis.gmail-sync.plist"
```

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

## Realtime voice

The homepage can connect your microphone to `gpt-realtime-2.1` for a spoken
conversation. The model uses the Cedar voice. Start the Python server in one
terminal from the project root:

```bash
.venv/bin/python examples/llm_example.py
```

In a second terminal:

```bash
cd frontend
npm run dev
```

Open `http://127.0.0.1:5173`, click **Talk to JARVIS**, allow microphone access,
and speak. Use **End conversation** to disconnect and release the microphone.
The audio playback controls can resume playback if your browser blocks autoplay.
Sessions also disconnect after five minutes. Realtime API usage is billed to
your OpenAI project while you use voice.

`examples/llm_example.py` loads the existing root `.env` and keeps
`OPENAI_API_KEY` server-side. The frontend requests a short-lived token through
Vite's `/api` proxy, then sends microphone audio directly to OpenAI over WebRTC.
Tokens and audio are not saved to files. Voice sessions can use `search_gmail`
and `read_gmail_email` to retrieve mail from `data/jarvis.db` on demand. Only
matching search rows and requested message text are returned to the model;
the full database is not uploaded. Search results use a compact tab-separated
table, and long message bodies can be read in pages.

`examples/gmail_tools.py` uses a read-only SQLite connection and fixed,
parameterized queries. Voice cannot send, delete, or change emails. The local
table is a partial snapshot. `gmail.received_at` stores Gmail's `internalDate`
as an ISO 8601 UTC timestamp, and searches return newest received emails first.
The importer adds the column to existing databases and updates rows on repeat
fetches, including their received timestamps.
`search_crowdmark` also retrieves course assessments and displayed scores from
`crowdmark`, using a read-only connection and compact result tables. Missing
scores are distinct from zero; course weights and final course grades are not
inferred. Calendar and weather tools are not connected yet.

The server binds only to `127.0.0.1:8765`. It is a local development server,
not an authenticated public backend. `/health` reports server health; the
frontend development and preview ports are fixed at 5173 and 4173.

Offline verification:

```bash
.venv/bin/python -m unittest discover -s tests -p test_voice_server.py -v
.venv/bin/python -m unittest discover -s tests -p test_gmail_tools.py -v
node --test frontend/tests/voiceToolCalls.test.js
```

Reference: [OpenAI Realtime WebRTC guide](https://developers.openai.com/api/docs/guides/voice-webrtc).

## Project layout

```text
scripts/
  fetch_gmail.py       # Download Gmail messages
  import_gmail.py      # Decode and load raw Gmail messages into SQLite
  fetch_calendar.py    # Download upcoming Calendar events
  import_calendar.py   # Load Calendar events into SQLite
examples/
  llm_example.py       # Local realtime voice token server
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

`examples/llm_example.py` loads `OPENAI_API_KEY` from the root `.env` and starts
a local server; it calls OpenAI only when a voice token is requested.
`examples/summarize_emails.py` makes an API request when run and expects
`OPENAI_API_KEY` to already be set in its environment.

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
