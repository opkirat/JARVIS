import json
import sqlite3

## Define Connection
connection = sqlite3.connect('jarvis.db')

connection.execute("""
CREATE TABLE IF NOT EXISTS gmail
(
id TEXT PRIMARY KEY
)
""")

with open("email.json") as file:
    emails = json.load(file)

for email in emails:
    connection.execute(
        "INSERT INTO gmail (id) VALUES (?) ON CONFLICT(id) DO NOTHING",
        ([email['id']])
        )

connection.commit()
connection.close()

