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

CREATE INDEX idx_comments_parent_id ON comments(parent_id);

CREATE INDEX idx_notes_entry_id ON notes(entry_id);

CREATE INDEX idx_notifications_user_id ON notifications(user_id);

CREATE INDEX idx_opportunities_owner_id ON opportunities(owner_id);

CREATE INDEX idx_opportunity_shares_user_id ON opportunity_shares(user_id);

CREATE UNIQUE INDEX idx_saved_views_default_per_user
    ON saved_views(created_by, entity)
    WHERE is_default = 1 AND deleted_at IS NULL;

CREATE INDEX idx_saved_views_created_by ON saved_views(created_by);

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

-- Revision 0007 appended the last three columns with ALTER TABLE ADD COLUMN,
-- which is where SQLite records them: after `deleted_at`, not where a rewrite
-- of this table would put them.
CREATE TABLE comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    note_id INTEGER NOT NULL REFERENCES notes(id),
    body TEXT NOT NULL,
    created_by INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    deleted_at TEXT
, parent_id INTEGER REFERENCES comments(id), resolved_at TEXT, resolved_by INTEGER REFERENCES users(id));

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
-- `read_at`/`grouped_key` were added by ALTER TABLE (revision 0003), which
-- rewrites sqlite_master's stored SQL by splicing the new column list in
-- before the closing paren rather than reformatting the whole statement --
-- hence the line break landing here instead of after a trailing comma.
, read_at TEXT, grouped_key TEXT);

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

CREATE TABLE opportunity_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    opportunity_id INTEGER NOT NULL REFERENCES opportunities(id),
    version_number INTEGER NOT NULL,
    name TEXT NOT NULL,
    account_name TEXT NOT NULL,
    value NUMERIC NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'USD',
    stage TEXT NOT NULL,
    expected_close_date TEXT,
    edited_by INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE (opportunity_id, version_number)
);

-- Milestone 3.3a (revision 0008): neither table is in
-- `app.soft_delete.USER_DATA_TABLES` -- a reaction and a watcher are toggle
-- state, hard-deleted like `sessions`, not soft-deleted content (D-130).
CREATE TABLE reactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    comment_id INTEGER NOT NULL REFERENCES comments(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    emoji TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE (comment_id, user_id, emoji)
);

CREATE TABLE saved_views (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_by INTEGER NOT NULL REFERENCES users(id),
    name TEXT NOT NULL,
    entity TEXT NOT NULL CHECK (entity IN ('opportunities', 'timeline')),
    filters TEXT NOT NULL DEFAULT '{}',
    sort TEXT NOT NULL DEFAULT '{}',
    group_by TEXT,
    is_shared INTEGER NOT NULL DEFAULT 0 CHECK (is_shared IN (0, 1)),
    is_default INTEGER NOT NULL DEFAULT 0 CHECK (is_default IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    deleted_at TEXT
);

CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    expires_at TEXT NOT NULL
);

-- Revision 0005_entry_types rebuilt this table to widen the CHECK constraint
-- (SQLite has no `ALTER TABLE ... ADD CHECK`), renaming a scratch table into
-- place rather than the original out of the way -- see the revision's
-- docstring. SQLite double-quotes a table's name in its own stored SQL after
-- a rename, which every other table here never goes through.
CREATE TABLE "timeline_entries" (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    opportunity_id INTEGER NOT NULL REFERENCES opportunities(id),
    type TEXT NOT NULL CHECK (type IN ('call', 'email', 'meeting', 'demo', 'proposal', 'contract', 'stage_change', 'other', 'site_visit', 'objection', 'competitor_intel')),
    title TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    event_timestamp TEXT NOT NULL,
    follow_up_date TEXT,
    created_by INTEGER REFERENCES users(id),
    system_generated INTEGER NOT NULL DEFAULT 0 CHECK (system_generated IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    deleted_at TEXT
);

CREATE TABLE timeline_entry_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id INTEGER NOT NULL REFERENCES timeline_entries(id),
    version_number INTEGER NOT NULL,
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    event_timestamp TEXT NOT NULL,
    follow_up_date TEXT,
    edited_by INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE (entry_id, version_number)
);

CREATE TABLE watchers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    opportunity_id INTEGER NOT NULL REFERENCES opportunities(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE (opportunity_id, user_id)
);

CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- Revision 0002_search_index (ADR 0007). The FTS5 virtual table, the four
-- shadow tables SQLite creates beneath it, and the nine triggers that keep the
-- index current -- including the soft-delete transitions.

CREATE VIRTUAL TABLE search_index USING fts5(
    title,
    body,
    content='',
    tokenize='porter unicode61'
);

CREATE TABLE 'search_index_config'(k PRIMARY KEY, v) WITHOUT ROWID;

CREATE TABLE 'search_index_data'(id INTEGER PRIMARY KEY, block BLOB);

CREATE TABLE 'search_index_docsize'(id INTEGER PRIMARY KEY, sz BLOB);

CREATE TABLE 'search_index_idx'(segid, term, pgno, PRIMARY KEY(segid, term)) WITHOUT ROWID;

CREATE TRIGGER timeline_entries_search_insert AFTER INSERT ON timeline_entries BEGIN
    INSERT INTO search_index(rowid, title, body)
    SELECT new.id * 4 + 0, new.title, new.body WHERE new.deleted_at IS NULL;
END;

CREATE TRIGGER timeline_entries_search_update AFTER UPDATE ON timeline_entries BEGIN
    INSERT INTO search_index(search_index, rowid, title, body)
    SELECT 'delete', old.id * 4 + 0, old.title, old.body WHERE old.deleted_at IS NULL;
    INSERT INTO search_index(rowid, title, body)
    SELECT new.id * 4 + 0, new.title, new.body WHERE new.deleted_at IS NULL;
END;

CREATE TRIGGER timeline_entries_search_delete AFTER DELETE ON timeline_entries BEGIN
    INSERT INTO search_index(search_index, rowid, title, body)
    SELECT 'delete', old.id * 4 + 0, old.title, old.body WHERE old.deleted_at IS NULL;
END;

CREATE TRIGGER notes_search_insert AFTER INSERT ON notes BEGIN
    INSERT INTO search_index(rowid, title, body)
    SELECT new.id * 4 + 1, '', new.body WHERE new.deleted_at IS NULL;
END;

CREATE TRIGGER notes_search_update AFTER UPDATE ON notes BEGIN
    INSERT INTO search_index(search_index, rowid, title, body)
    SELECT 'delete', old.id * 4 + 1, '', old.body WHERE old.deleted_at IS NULL;
    INSERT INTO search_index(rowid, title, body)
    SELECT new.id * 4 + 1, '', new.body WHERE new.deleted_at IS NULL;
END;

CREATE TRIGGER notes_search_delete AFTER DELETE ON notes BEGIN
    INSERT INTO search_index(search_index, rowid, title, body)
    SELECT 'delete', old.id * 4 + 1, '', old.body WHERE old.deleted_at IS NULL;
END;

CREATE TRIGGER comments_search_insert AFTER INSERT ON comments BEGIN
    INSERT INTO search_index(rowid, title, body)
    SELECT new.id * 4 + 2, '', new.body WHERE new.deleted_at IS NULL;
END;

CREATE TRIGGER comments_search_update AFTER UPDATE ON comments BEGIN
    INSERT INTO search_index(search_index, rowid, title, body)
    SELECT 'delete', old.id * 4 + 2, '', old.body WHERE old.deleted_at IS NULL;
    INSERT INTO search_index(rowid, title, body)
    SELECT new.id * 4 + 2, '', new.body WHERE new.deleted_at IS NULL;
END;

CREATE TRIGGER comments_search_delete AFTER DELETE ON comments BEGIN
    INSERT INTO search_index(search_index, rowid, title, body)
    SELECT 'delete', old.id * 4 + 2, '', old.body WHERE old.deleted_at IS NULL;
END;

-- Revision 0009_tasks (milestone 4.1): action items scoped to an opportunity.
-- `completed_at`/`completed_by` rather than a boolean done flag, for the reason
-- revision 0003 gave `notifications.read_at`; `due_date` is a date because
-- "call them back Thursday" has no time of day.
CREATE TABLE tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    opportunity_id INTEGER NOT NULL REFERENCES opportunities(id),
    entry_id INTEGER REFERENCES timeline_entries(id),
    title TEXT NOT NULL,
    assignee_id INTEGER REFERENCES users(id),
    due_date TEXT,
    completed_at TEXT,
    completed_by INTEGER REFERENCES users(id),
    created_by INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    deleted_at TEXT
);

CREATE INDEX idx_tasks_opportunity ON tasks (opportunity_id, due_date, id);

CREATE INDEX idx_tasks_assignee ON tasks (assignee_id, completed_at, due_date, id);
