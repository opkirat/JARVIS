import json
import sqlite3
import base64
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def get_body_data(payload):
    if payload.get("body", {}).get("data"):
        return payload["body"]["data"]

    for part in payload.get("parts", []):
        data = get_body_data(part)
        if data:
            return data

    return ""

## Define Connection
def import_emails(emails):
    connection = sqlite3.connect(PROJECT_ROOT / "data" / "jarvis.db")
    connection.execute("""
    CREATE TABLE IF NOT EXISTS gmail
    (
        id TEXT PRIMARY KEY,
        snippet TEXT,
        labelIds TEXT,
        delivered TEXT,
        sender TEXT,
        subject TEXT,
        body TEXT,
        received_at TEXT
    )
    """)
    columns = {row[1] for row in connection.execute("PRAGMA table_info(gmail)")}
    if "received_at" not in columns:
        connection.execute("ALTER TABLE gmail ADD COLUMN received_at TEXT")

    for email in emails:
        received_at = datetime.fromtimestamp(
            int(email["internalDate"]) / 1000, tz=timezone.utc
        ).isoformat(timespec="milliseconds")
        delivered = None ## So Delivered doesn't become undefined
        sender = None
        subject = None
        body = get_body_data(email["payload"])
        body += "=" * (-len(body) % 4)
        body = base64.urlsafe_b64decode(body).decode(
            "utf-8", errors="replace"
        )

        headers = email["payload"]["headers"]
        for header in headers:
            if header["name"].lower() == "delivered-to":
                delivered = header["value"]

            elif header["name"].lower() == "from":
                sender = header["value"]

            elif header["name"].lower() == "subject":
                subject = header["value"]

        connection.execute(
        """INSERT INTO gmail
        (id, snippet, labelIds, delivered, sender, subject, body, received_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            snippet = excluded.snippet,
            labelIds = excluded.labelIds,
            delivered = excluded.delivered,
            sender = excluded.sender,
            subject = excluded.subject,
            body = excluded.body,
            received_at = excluded.received_at""",
        (
            email['id'],
             email['snippet'],
             json.dumps(email['labelIds']),
             delivered,
             sender,
             subject,
             body,
             received_at
             )
            )
    connection.commit()
    connection.close()
