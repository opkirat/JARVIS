"""Read-only Crowdmark searches using synthetic assessment data."""

import csv
import io
import sqlite3
import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from examples import crowdmark_tools


class CrowdmarkToolsTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'jarvis.db'
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute('CREATE TABLE crowdmark (course_title TEXT, assesment_title TEXT, score TEXT, url TEXT)')
            connection.executemany('INSERT INTO crowdmark VALUES (?, ?, ?, ?)', [
                ('MATH 135', 'Assignment 1', '18 / 20', 'https://example.com/1'),
                ('MATH 135', 'Assignment 2', '0%', 'https://example.com/2'),
                ('MATH 135', 'Assignment 3', None, 'https://example.com/3'),
                ('CS 135', 'Quiz 1', '9 / 10', 'https://example.com/4'),
            ])
            connection.commit()
        self.patcher = patch.object(crowdmark_tools, 'DATABASE_PATH', self.path)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_course_search_and_pagination(self):
        result = crowdmark_tools.lookup_crowdmark('search_crowdmark', {'query': 'math 135', 'limit': 2})
        self.assertEqual(result['total_matches'], 3)
        self.assertEqual(result['next_offset'], 2)
        rows = list(csv.reader(io.StringIO(result['assessments_table']), delimiter='\t'))
        self.assertEqual(rows[0], ['course', 'assessment', 'score', 'url'])
        self.assertEqual(rows[1][2], '18 / 20')
        page = crowdmark_tools.lookup_crowdmark('search_crowdmark', {'query': 'math 135', 'limit': 2, 'offset': 2})
        self.assertIsNone(page['next_offset'])
        self.assertEqual(page['count'], 1)

    def test_missing_score_is_distinct_from_zero(self):
        result = crowdmark_tools.lookup_crowdmark('search_crowdmark', {'query': 'math'})
        rows = list(csv.reader(io.StringIO(result['assessments_table']), delimiter='\t'))
        self.assertEqual(rows[2][2], '0%')
        self.assertEqual(rows[3][2], '(not available)')

    def test_injection_does_not_match_everything(self):
        result = crowdmark_tools.lookup_crowdmark('search_crowdmark', {'query': "' OR 1=1 --"})
        self.assertEqual(result['total_matches'], 0)

    def test_rejects_unknown_tools_and_unbounded_queries(self):
        for name, args in [
            ('execute_sql', {}),
            ('search_crowdmark', {'query': '', 'limit': 999}),
            ('search_crowdmark', {'query': '', 'offset': -1}),
            ('search_crowdmark', {'query': '', 'limit': True}),
            ('search_crowdmark', {'query': '', 'sql': 'DELETE FROM crowdmark'}),
        ]:
            with self.assertRaises(crowdmark_tools.CrowdmarkToolError):
                crowdmark_tools.lookup_crowdmark(name, args)

    def test_database_is_unchanged_by_lookup(self):
        before = self.path.read_bytes()
        crowdmark_tools.lookup_crowdmark('search_crowdmark', {'query': ''})
        self.assertEqual(self.path.read_bytes(), before)

    def test_missing_database_is_not_created(self):
        missing = Path(self.directory.name) / 'missing.db'
        with patch.object(crowdmark_tools, 'DATABASE_PATH', missing):
            with self.assertRaises(crowdmark_tools.CrowdmarkToolError):
                crowdmark_tools.lookup_crowdmark('search_crowdmark', {'query': ''})
        self.assertFalse(missing.exists())


if __name__ == '__main__':
    unittest.main()
