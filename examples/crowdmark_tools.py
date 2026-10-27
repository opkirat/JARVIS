"""Read-only assessment and score lookups from the existing Crowdmark table."""

import csv
import io
import sqlite3
from contextlib import closing
from pathlib import Path

DATABASE_PATH = Path(__file__).resolve().parent.parent / 'data' / 'jarvis.db'
TOOLS = [{
    'type': 'function',
    'name': 'search_crowdmark',
    'description': (
        'Look up stored Crowdmark assessments and their displayed scores. '
        'Search course names and assessment titles; all query terms must match. '
        'Use an empty query to list assessments across courses. Supports pagination. '
        'Scores are stored as displayed text; missing scores are not zero. '
        'Course weights and final course grades are not available.'
    ),
    'parameters': {
        'type': 'object',
        'properties': {
            'query': {'type': 'string', 'maxLength': 200},
            'limit': {'type': 'integer', 'minimum': 1, 'maximum': 50},
            'offset': {'type': 'integer', 'minimum': 0, 'maximum': 10000},
        },
        'required': ['query'],
        'additionalProperties': False,
    },
}]


class CrowdmarkToolError(ValueError):
    pass


def lookup_crowdmark(name, arguments):
    if name != 'search_crowdmark':
        raise CrowdmarkToolError('Unknown Crowdmark tool.')
    if not isinstance(arguments, dict) or set(arguments) - {'query', 'limit', 'offset'}:
        raise CrowdmarkToolError('Invalid Crowdmark search arguments.')
    query = arguments.get('query', '')
    limit = arguments.get('limit', 10)
    offset = arguments.get('offset', 0)
    if not isinstance(query, str) or len(query) > 200:
        raise CrowdmarkToolError('Search query must be text of at most 200 characters.')
    if type(limit) is not int or not 1 <= limit <= 50:
        raise CrowdmarkToolError('limit must be an integer between 1 and 50.')
    if type(offset) is not int or not 0 <= offset <= 10000:
        raise CrowdmarkToolError('offset must be an integer between 0 and 10000.')

    clauses = []
    parameters = []
    for term in query.split():
        escaped = term.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        # assesment_title is the existing database column's spelling.
        clauses.append("(COALESCE(course_title, '') || ' ' || COALESCE(assesment_title, '')) LIKE ? ESCAPE '\\'")
        parameters.append(f'%{escaped}%')
    where = ' AND '.join(clauses) or '1 = 1'
    try:
        with closing(sqlite3.connect(DATABASE_PATH.resolve().as_uri() + '?mode=ro', uri=True, timeout=5)) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute('PRAGMA query_only = ON')
            total = connection.execute(f'SELECT COUNT(*) FROM crowdmark WHERE {where}', parameters).fetchone()[0]
            rows = connection.execute(
                f'''SELECT course_title, assesment_title AS assessment_title, score, url
                    FROM crowdmark WHERE {where}
                    ORDER BY course_title COLLATE NOCASE, assesment_title COLLATE NOCASE, rowid
                    LIMIT ? OFFSET ?''',
                [*parameters, limit, offset],
            ).fetchall()
        output = io.StringIO(newline='')
        writer = csv.writer(output, delimiter='\t', lineterminator='\n')
        writer.writerow(['course', 'assessment', 'score', 'url'])
        for row in rows:
            writer.writerow([
                (row['course_title'] or '')[:500], (row['assessment_title'] or '')[:500],
                '(not available)' if row['score'] is None or row['score'] == '' else row['score'],
                row['url'] or '',
            ])
        return {
            'assessments_table': output.getvalue(), 'total_matches': total, 'count': len(rows),
            'next_offset': offset + len(rows) if offset + len(rows) < total else None,
            'source': 'local Crowdmark snapshot; displayed scores only, no course weights',
        }
    except sqlite3.Error:
        raise CrowdmarkToolError('The local Crowdmark table is unavailable. Import Crowdmark scores and try again.') from None
