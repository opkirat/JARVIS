# JARVIS

A personal assistant project, starting with Gmail exports and a local SQLite database.

## Project layout

```text
scripts/
  fetch_gmail.py       # Download Gmail messages
  clean_gmail.py       # Decode messages into a cleaned JSON export (probably to be deleted)
  import_gmail.py      # Decode and load raw Gmail messages into SQLite
  llm_example.py       # Standalone model API example
sql/
  list_emails.sql      # Query the Gmail table
data/                 # Local files; excluded from Git
  gmail/
    raw_emails.json
    sample_emails.json
    cleaned_emails.json
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

Optionally create a cleaned JSON export:

```bash
python scripts/clean_gmail.py
```

Import the raw export into SQLite (the cleaner is not required first):

```bash
python scripts/import_gmail.py
```

The importer currently drops and rebuilds the `gmail` table each time. Manual changes to that table are overwritten.

Run the saved query:

```bash
sqlite3 -header -column data/jarvis.db ".read sql/list_emails.sql"
```

The Gmail scripts resolve data and credential paths relative to the project location, so those paths also work when the scripts are launched from another directory.

`scripts/llm_example.py` makes an API request when run and expects `OPENAI_API_KEY` in the environment. It does not load `.env` itself.
