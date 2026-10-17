import json
import sqlite3
import base64
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

## Define Connection
connection = sqlite3.connect(PROJECT_ROOT / "data" / "jarvis.db")

## Drop table if needed
connection.execute("DROP TABLE IF EXISTS gmail")


connection.execute("""
CREATE TABLE IF NOT EXISTS gmail
(
    id TEXT PRIMARY KEY,
    snippet TEXT,
    labelIds TEXT,
    delivered TEXT,
    sender TEXT,
    subject TEXT,
    body TEXT
)
""")

with open(PROJECT_ROOT / "data" / "gmail" / "raw_emails.json") as file:
    emails = json.load(file)

def get_body_data(payload):
    if payload.get("body", {}).get("data"):
        return payload["body"]["data"]

    for part in payload.get("parts", []):
        data = get_body_data(part)
        if data:
            return data

    return ""

for email in emails:
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
    "INSERT INTO gmail (id, snippet, labelIds, delivered, sender, subject, body) VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO NOTHING",
    (
        email['id'],
         email['snippet'],
         json.dumps(email['labelIds']),  
         delivered,
         sender,
         subject,
         body
         )
        )
connection.commit()
connection.close()