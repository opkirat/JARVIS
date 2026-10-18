import json
import sqlite3
import base64
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

## Define Connection
connection = sqlite3.connect(PROJECT_ROOT / "data" / "jarvis.db")

## Drop table if needed
##connection.execute("DROP TABLE IF EXISTS calendar"



connection.execute("""
CREATE TABLE IF NOT EXISTS calendar
(
    id TEXT PRIMARY KEY,
    created TEXT,
    updated TEXT,
    summary TEXT,
    description TEXT,
    location TEXT,
    start TEXT,
    end TEXT,
    all_day TEXT
)
""")

with open(PROJECT_ROOT / "data" / "gmail" / "raw_calendars.json") as file:
    events = json.load(file)

for event in events:
    start = event["start"].get("dateTime") or event["start"].get("date")
    end = event["end"].get("dateTime") or event["end"].get("date")
    all_day = "date" in event["start"]
    location = event.get("location")


    connection.execute(
    "INSERT INTO calendar (id, created, updated, summary, description, location, start, end, all_day) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO NOTHING",
    (
        event['id'],
        event['created'],
        event['updated'],
        event['summary'],
        event['description'],
        location,
        start,
        end,
        all_day
         )
        )
connection.commit()
connection.close()