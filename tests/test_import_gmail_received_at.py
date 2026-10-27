"""Verify received-date migration and backfilling when existing mail is fetched."""

import importlib.util
import sqlite3
import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('gmail_importer', Path(__file__).resolve().parent.parent / 'scripts/import_gmail.py')
importer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(importer)


class ReceivedDateTests(unittest.TestCase):
    def test_migrates_old_table_and_updates_existing_email(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'data').mkdir()
            database = root / 'data/jarvis.db'
            with closing(sqlite3.connect(database)) as connection:
                connection.execute('CREATE TABLE gmail (id TEXT PRIMARY KEY, snippet TEXT, labelIds TEXT, delivered TEXT, sender TEXT, subject TEXT, body TEXT)')
                connection.execute("INSERT INTO gmail (id, subject) VALUES ('synthetic', 'old subject')")
                connection.commit()
            email = {
                'id': 'synthetic', 'snippet': '', 'labelIds': ['INBOX'],
                'internalDate': '1767225600123',
                'payload': {'headers': [{'name': 'Subject', 'value': 'updated subject'}], 'body': {'data': ''}},
            }
            with patch.object(importer, 'PROJECT_ROOT', root):
                importer.import_emails([email])
                importer.import_emails([email])
            with closing(sqlite3.connect(database)) as connection:
                rows = connection.execute('SELECT id, subject, received_at FROM gmail').fetchall()
            self.assertEqual(rows, [('synthetic', 'updated subject', '2026-01-01T00:00:00.123+00:00')])


if __name__ == '__main__':
    unittest.main()
