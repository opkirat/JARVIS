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
CREATE TABLE IF NOT EXISTS crowdmark
(
    course_title TEXT,
    assesment_title TEXT,
    score TEXT,
    url TEXT
    
    )
""")

with open(PROJECT_ROOT / "data" / "crowdmark" / "scores.json") as file:
    scores = json.load(file)
    grades = scores["courses"]

for grade in grades:
    course_title = grade['title']
    assessments = grade["assessments"]
    for assessment in assessments:    
        assessment_title = assessment['title']
        score = assessment['score']
        url = assessment['url']


        connection.execute(
    "INSERT INTO crowdmark (course_title, assesment_title, score, url) VALUES (?, ?, ?, ?)",
    (
            course_title,
            assessment_title,
            score,
            url
         )
        )
connection.commit()
connection.close()