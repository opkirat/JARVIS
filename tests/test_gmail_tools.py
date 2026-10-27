"""Exercise real SQLite lookups using synthetic mail in a temporary database."""

import csv
import io
import sqlite3
import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from examples import gmail_tools


class GmailToolsTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'jarvis.db'
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute('CREATE TABLE gmail (id TEXT PRIMARY KEY, sender TEXT, subject TEXT, snippet TEXT, body TEXT, received_at TEXT)')
            connection.executemany('INSERT INTO gmail VALUES (?, ?, ?, ?, ?, ?)', [
                ('one', 'math@example.com', 'Assignment', 'Due Monday', 'Math homework is due Monday.', '2026-10-26T12:00:00.000+00:00'),
                ('two', 'school@example.com', 'Meeting', 'Office hours', 'Bring your math questions.', '2026-10-25T12:00:00.000+00:00'),
                ('three', 'sales@example.com', 'Save 10%', 'A literal discount', 'x' * 9000, '2026-10-24T12:00:00.000+00:00'),
            ])
            connection.commit()
        self.patcher = patch.object(gmail_tools, 'DATABASE_PATH', self.path)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_search_filters_and_paginates_compact_table(self):
        result = gmail_tools.lookup_gmail('search_gmail', {'query': 'math', 'limit': 1})
        self.assertEqual(result['total_matches'], 2)
        self.assertEqual(result['next_offset'], 1)
        rows = list(csv.reader(io.StringIO(result['emails_table']), delimiter='\t'))
        self.assertEqual(rows[1][0], 'one')
        self.assertEqual(rows[1][1], '2026-10-26T12:00:00.000+00:00')
        result = gmail_tools.lookup_gmail('search_gmail', {'query': 'math', 'limit': 1, 'offset': 1})
        self.assertIsNone(result['next_offset'])
        self.assertIn('two', result['emails_table'])

    def test_search_is_parameterized_and_wildcards_are_literal(self):
        self.assertEqual(gmail_tools.lookup_gmail('search_gmail', {'query': "' OR 1=1 --"})['total_matches'], 0)
        self.assertEqual(gmail_tools.lookup_gmail('search_gmail', {'query': '%'})['total_matches'], 1)

    def test_body_pagination_and_missing_message(self):
        first = gmail_tools.lookup_gmail('read_gmail_email', {'id': 'three'})
        self.assertEqual(len(first['body']), 8000)
        self.assertEqual(first['next_body_offset'], 8000)
        self.assertEqual(first['received_at'], '2026-10-24T12:00:00.000+00:00')
        second = gmail_tools.lookup_gmail('read_gmail_email', {'id': 'three', 'body_offset': 8000})
        self.assertEqual(len(second['body']), 1000)
        self.assertIsNone(second['next_body_offset'])
        self.assertIn('error', gmail_tools.lookup_gmail('read_gmail_email', {'id': 'missing'}))

    def test_rejects_arbitrary_tools_and_invalid_arguments(self):
        for name, args in [
            ('execute_sql', {'sql': 'DELETE FROM gmail'}),
            ('search_gmail', {'query': '', 'limit': -1}),
            ('search_gmail', {'query': '', 'limit': True}),
            ('search_gmail', {'query': '', 'sql': 'DELETE FROM gmail'}),
            ('read_gmail_email', {'id': 'one', 'body_offset': -1}),
        ]:
            with self.assertRaises(gmail_tools.GmailToolError):
                gmail_tools.lookup_gmail(name, args)

    def test_reads_leave_database_unchanged(self):
        before = self.path.read_bytes()
        gmail_tools.lookup_gmail('search_gmail', {'query': ''})
        gmail_tools.lookup_gmail('read_gmail_email', {'id': 'one'})
        self.assertEqual(self.path.read_bytes(), before)

    def test_missing_database_is_not_created(self):
        missing = Path(self.directory.name) / 'missing.db'
        with patch.object(gmail_tools, 'DATABASE_PATH', missing):
            with self.assertRaises(gmail_tools.GmailToolError):
                gmail_tools.lookup_gmail('search_gmail', {'query': ''})
        self.assertFalse(missing.exists())


if __name__ == '__main__':
    unittest.main()
