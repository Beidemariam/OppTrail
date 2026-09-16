-- Expected schema snapshot, used by tests/test_migrations.py.
--
-- Captured from the accepted MVP's `app/schema.sql` before it was replaced by
-- the Alembic baseline revision (ADR 0002). `alembic upgrade head` against an
-- empty database must reproduce exactly this, so a revision that changes the
-- schema has to update this file deliberately.
--
-- Statements are the `sqlite_master.sql` text with `IF NOT EXISTS` removed and
-- whitespace collapsed by the test; formatting here is for review only.

CREATE INDEX idx_audit_log_entries_opportunity_id ON audit_log_entries(opportunity_id);

CREATE INDEX idx_comments_note_id ON comments(note_id);

CREATE INDEX idx_notes_entry_id ON notes(entry_id);

CREATE INDEX idx_notifications_user_id ON notifications(user_id);

CREATE INDEX idx_opportunities_owner_id ON opportunities(owner_id);

CREATE INDEX idx_opportunity_shares_user_id ON opportunity_shares(user_id);

CREATE INDEX idx_sessions_expires_at ON sessions(expires_at);

CREATE INDEX idx_sessions_user_id ON sessions(user_id);

CREATE INDEX idx_timeline_entries_opportunity_id ON timeline_entries(opportunity_id);

CREATE TABLE audit_log_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    opportunity_id INTEGER NOT NULL REFERENCES opportunities(id),
    actor_id INTEGER REFERENCES users(id),
    action TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    note_id INTEGER NOT NULL REFERENCES notes(id),
    body TEXT NOT NULL,
    created_by INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    deleted_at TEXT
);

CREATE TABLE note_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    note_id INTEGER NOT NULL REFERENCES notes(id),
    version_number INTEGER NOT NULL,
    body TEXT NOT NULL,
    edited_by INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE (note_id, version_number)
);

CREATE TABLE notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id INTEGER NOT NULL REFERENCES timeline_entries(id),
    body TEXT NOT NULL,
    created_by INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    edited INTEGER NOT NULL DEFAULT 0 CHECK (edited IN (0, 1)),
    deleted_at TEXT
);

CREATE TABLE notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    type TEXT NOT NULL,
    payload TEXT NOT NULL DEFAULT '{}',
    read INTEGER NOT NULL DEFAULT 0 CHECK (read IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE opportunities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    account_name TEXT NOT NULL,
    value NUMERIC NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'USD',
    stage TEXT NOT NULL DEFAULT 'Prospecting'
        CHECK (stage IN (
            'Prospecting',
            'Qualification',
            'Needs Analysis',
            'Proposal',
            'Negotiation',
            'Closed Won',
            'Closed Lost'
        )),
    owner_id INTEGER NOT NULL REFERENCES users(id),
    expected_close_date TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    deleted_at TEXT
);

CREATE TABLE opportunity_shares (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    opportunity_id INTEGER NOT NULL REFERENCES opportunities(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    role TEXT NOT NULL CHECK (role IN ('viewer', 'editor')),
    invited_by INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    deleted_at TEXT,
    UNIQUE (opportunity_id, user_id)
);

CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    expires_at TEXT NOT NULL
);

CREATE TABLE timeline_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    opportunity_id INTEGER NOT NULL REFERENCES opportunities(id),
    type TEXT NOT NULL CHECK (type IN (
        'call',
        'email',
        'meeting',
        'demo',
        'proposal',
        'contract',
        'stage_change',
        'other'
    )),
    title TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    event_timestamp TEXT NOT NULL,
    follow_up_date TEXT,
    created_by INTEGER REFERENCES users(id),
    system_generated INTEGER NOT NULL DEFAULT 0 CHECK (system_generated IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    deleted_at TEXT
);

CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
