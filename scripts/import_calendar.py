import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def import_events(events):
    database_path = PROJECT_ROOT / "data" / "jarvis.db"
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    try:
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

        for event in events:
            start = event["start"].get("dateTime") or event["start"].get("date")
            end = event["end"].get("dateTime") or event["end"].get("date")
            all_day = "date" in event["start"]
            location = event.get("location")


            connection.execute(
            "INSERT INTO calendar (id, created, updated, summary, description, location, start, end, all_day) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO NOTHING",
            (
                event['id'],
                event.get('created'),
                event.get('updated'),
                event.get('summary'),
                event.get('description'),
                location,
                start,
                end,
                all_day
                 )
                )
        connection.commit()
    finally:
        connection.close()
