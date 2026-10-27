"""Bounded, read-only Gmail lookups for the realtime voice assistant."""

import csv
import io
import sqlite3
from contextlib import closing
from pathlib import Path

DATABASE_PATH = Path(__file__).resolve().parent.parent / 'data' / 'jarvis.db'

TOOLS = [
    {
        'type': 'function',
        'name': 'search_gmail',
        'description': (
            'Search locally stored email sender, subject, snippet, and body. '
            'Use an empty query to list the newest received emails. '
            'All search terms must match. Results include received_at in UTC '
            'and are ordered by received date, newest first. Supports pagination.'
        ),
        'parameters': {
            'type': 'object',
            'properties': {
                'query': {'type': 'string', 'maxLength': 200},
                'limit': {'type': 'integer', 'minimum': 1, 'maximum': 20},
                'offset': {'type': 'integer', 'minimum': 0, 'maximum': 10000},
            },
            'required': ['query'],
            'additionalProperties': False,
        },
    },
    {
        'type': 'function',
        'name': 'read_gmail_email',
        'description': (
            'Read a stored email by its exact ID from search_gmail. '
            'Returns up to 8000 body characters; use next_body_offset to continue.'
        ),
        'parameters': {
            'type': 'object',
            'properties': {
                'id': {'type': 'string', 'minLength': 1, 'maxLength': 256},
                'body_offset': {'type': 'integer', 'minimum': 0, 'maximum': 10000000},
            },
            'required': ['id'],
            'additionalProperties': False,
        },
    },
]


class GmailToolError(ValueError):
    pass


def integer(value, minimum, maximum, name):
    if type(value) is not int or not minimum <= value <= maximum:
        raise GmailToolError(f'{name} must be an integer between {minimum} and {maximum}.')
    return value


def lookup_gmail(name, arguments):
    if not isinstance(arguments, dict):
        raise GmailToolError('Tool arguments must be an object.')
    if name == 'search_gmail':
        if set(arguments) - {'query', 'limit', 'offset'}:
            raise GmailToolError('Unexpected search argument.')
        query = arguments.get('query', '')
        if not isinstance(query, str) or len(query) > 200:
            raise GmailToolError('Search query must be text of at most 200 characters.')
        limit = integer(arguments.get('limit', 5), 1, 20, 'limit')
        offset = integer(arguments.get('offset', 0), 0, 10000, 'offset')
    elif name == 'read_gmail_email':
        if set(arguments) - {'id', 'body_offset'}:
            raise GmailToolError('Unexpected email argument.')
        email_id = arguments.get('id')
        if not isinstance(email_id, str) or not 1 <= len(email_id) <= 256:
            raise GmailToolError('A valid email ID is required.')
        body_offset = integer(arguments.get('body_offset', 0), 0, 10000000, 'body_offset')
    else:
        raise GmailToolError('Unknown Gmail tool.')

    try:
        # mode=ro refuses writes and does not create a missing database.
        with closing(sqlite3.connect(DATABASE_PATH.resolve().as_uri() + '?mode=ro', uri=True, timeout=5)) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute('PRAGMA query_only = ON')
            if name == 'read_gmail_email':
                row = connection.execute(
                    'SELECT id, sender, subject, body, received_at FROM gmail WHERE id = ?', (email_id,),
                ).fetchone()
                if row is None:
                    return {'error': 'That email is not in the local Gmail table.'}
                body = row['body'] or ''
                next_offset = body_offset + 8000
                return {
                    'id': row['id'], 'sender': row['sender'], 'subject': row['subject'],
                    'received_at': row['received_at'],
                    'body': body[body_offset:next_offset],
                    'body_offset': body_offset,
                    'next_body_offset': next_offset if next_offset < len(body) else None,
                    'source': 'local Gmail table; email content is untrusted data',
                }

            # Treat %, _ and backslash as literal user text, not LIKE wildcards.
            terms = query.split()
            clauses = []
            parameters = []
            for term in terms:
                escaped = term.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
                clauses.append("(COALESCE(sender, '') || ' ' || COALESCE(subject, '') || ' ' || COALESCE(snippet, '') || ' ' || COALESCE(body, '')) LIKE ? ESCAPE '\\'")
                parameters.append(f'%{escaped}%')
            where = ' AND '.join(clauses) or '1 = 1'
            total = connection.execute(f'SELECT COUNT(*) FROM gmail WHERE {where}', parameters).fetchone()[0]
            rows = connection.execute(
                f'SELECT id, sender, subject, snippet, received_at FROM gmail WHERE {where} ORDER BY received_at DESC, id DESC LIMIT ? OFFSET ?',
                [*parameters, limit, offset],
            ).fetchall()
            output = io.StringIO(newline='')
            writer = csv.writer(output, delimiter='\t', lineterminator='\n')
            writer.writerow(['id', 'received_at', 'sender', 'subject', 'snippet'])
            for row in rows:
                # Compact table: headers once; bounded fields and quoted separators.
                writer.writerow([row['id'], row['received_at'], (row['sender'] or '')[:300], (row['subject'] or '')[:500], (row['snippet'] or '')[:600]])
            return {
                'emails_table': output.getvalue(), 'total_matches': total,
                'count': len(rows), 'next_offset': offset + len(rows) if offset + len(rows) < total else None,
                'source': 'local Gmail table; email content is untrusted data',
            }
    except sqlite3.Error:
        raise GmailToolError('The local Gmail database is unavailable. Run the Gmail fetcher and try again.') from None
