-- Expected schema snapshot, used by tests/test_migrations.py.
--
-- Captured from the accepted MVP's `app/schema.sql` before it was replaced by
-- the Alembic baseline revision (ADR 0002). `alembic upgrade head` against an
-- empty database must reproduce exactly this, so a revision that changes the
-- schema has to update this file deliberately.
--
-- Statements are the `sqlite_master.sql` text with `IF NOT EXISTS` removed and
-- whitespace collapsed by the test; formatting here is for review only.

CREATE INDEX idx_attachments_entry
            ON attachments (entry_id, created_at, id);

CREATE INDEX idx_audit_log_entries_opportunity_id ON audit_log_entries(opportunity_id);

CREATE INDEX idx_automation_rules_armed
        ON automation_rules (trigger_type, id)
        WHERE archived_at IS NULL AND enabled = 1;

CREATE INDEX idx_automation_rules_creator
        ON automation_rules (created_by, id)
        WHERE archived_at IS NULL;

CREATE INDEX idx_automation_runs_entry
        ON automation_runs (entry_id, rule_id)
        WHERE entry_id IS NOT NULL;

CREATE INDEX idx_automation_runs_rule
        ON automation_runs (rule_id, id);

CREATE INDEX idx_comments_activity ON comments (note_id, created_at);

CREATE INDEX idx_comments_created_author
            ON comments (created_at, created_by);

CREATE INDEX idx_comments_note_id ON comments(note_id);

CREATE INDEX idx_comments_parent_id ON comments(parent_id);

CREATE INDEX idx_custom_field_definitions_live
        ON custom_field_definitions (entity_type, position, id)
        WHERE archived_at IS NULL;

CREATE UNIQUE INDEX idx_custom_field_key_per_entity
        ON custom_field_definitions (entity_type, key)
        WHERE archived_at IS NULL;

CREATE INDEX idx_job_runs_latest
        ON job_runs (job, id DESC);

CREATE INDEX idx_notes_activity ON notes (entry_id, created_at);

CREATE INDEX idx_notes_created_author
            ON notes (created_at, created_by);

CREATE INDEX idx_notes_entry_id ON notes(entry_id);

CREATE INDEX idx_notifications_user_id ON notifications(user_id);

CREATE INDEX idx_opportunities_last_activity
        ON opportunities (last_activity_at);

CREATE INDEX idx_opportunities_owner_id ON opportunities(owner_id);

CREATE INDEX idx_opportunity_shares_user_id ON opportunity_shares(user_id);

CREATE UNIQUE INDEX idx_private_notes_owner
        ON private_notes (opportunity_id, user_id)
        WHERE deleted_at IS NULL;

CREATE INDEX idx_saved_views_created_by ON saved_views(created_by);

CREATE UNIQUE INDEX idx_saved_views_default_per_user
            ON saved_views(created_by, entity)
            WHERE is_default = 1 AND deleted_at IS NULL;

CREATE INDEX idx_sessions_expires_at ON sessions(expires_at);

CREATE INDEX idx_sessions_user_id ON sessions(user_id);

CREATE INDEX idx_task_assignees_user ON task_assignees (user_id, task_id);

CREATE INDEX idx_task_comments_task
            ON task_comments (task_id, created_at, id);

CREATE INDEX idx_tasks_assignee
            ON tasks (assignee_id, completed_at, due_date, id);

CREATE INDEX idx_tasks_opportunity
            ON tasks (opportunity_id, due_date, id);

CREATE INDEX idx_timeline_entries_activity
        ON timeline_entries (opportunity_id, event_timestamp);

CREATE INDEX idx_timeline_entries_created_author
            ON timeline_entries (created_at, created_by);

CREATE INDEX idx_timeline_entries_opportunity_id ON timeline_entries(opportunity_id);

CREATE INDEX idx_timeline_entries_stage_changes
        ON timeline_entries (opportunity_id, event_timestamp, id)
        WHERE type = 'stage_change';

CREATE TABLE attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id INTEGER NOT NULL REFERENCES timeline_entries(id),
            sha256 TEXT NOT NULL,
            filename TEXT NOT NULL,
            content_type TEXT NOT NULL,
            byte_size INTEGER NOT NULL,
            uploaded_by INTEGER NOT NULL REFERENCES users(id),
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            deleted_at TEXT
        );

CREATE TABLE audit_log_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            opportunity_id INTEGER NOT NULL REFERENCES opportunities(id),
            actor_id INTEGER REFERENCES users(id),
            action TEXT NOT NULL,
            detail TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        );

CREATE TABLE automation_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            trigger_type TEXT NOT NULL CHECK (trigger_type IN (
                'stage_changed',
                'entry_created',
                'field_changed',
                'no_activity',
                'close_date_approaching'
            )),
            trigger_config TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(trigger_config)),
            conditions TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(conditions)),
            action_type TEXT NOT NULL CHECK (action_type IN (
                'create_task',
                'notify_user',
                'add_entry',
                'change_stage'
            )),
            action_config TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(action_config)),
            enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
            created_by INTEGER NOT NULL REFERENCES users(id),
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            archived_at TEXT
        );

CREATE TABLE automation_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_id INTEGER NOT NULL REFERENCES automation_rules(id),
            opportunity_id INTEGER NOT NULL REFERENCES opportunities(id),
            outcome TEXT NOT NULL CHECK (outcome IN ('applied', 'skipped', 'failed')),
            reason TEXT,
            entry_id INTEGER REFERENCES timeline_entries(id),
            dry_run INTEGER NOT NULL DEFAULT 0 CHECK (dry_run IN (0, 1)),
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        );

CREATE TABLE comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            note_id INTEGER NOT NULL REFERENCES notes(id),
            body TEXT NOT NULL,
            created_by INTEGER NOT NULL REFERENCES users(id),
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            deleted_at TEXT
        , parent_id INTEGER REFERENCES comments(id), resolved_at TEXT, resolved_by INTEGER REFERENCES users(id));

CREATE TABLE custom_field_definitions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT NOT NULL CHECK (entity_type IN ('opportunity', 'entry')),
            key TEXT NOT NULL,
            label TEXT NOT NULL,
            type TEXT NOT NULL CHECK (
                type IN ('text', 'number', 'date', 'select', 'multi_select', 'checkbox', 'user')
            ),
            options TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(options)),
            required INTEGER NOT NULL DEFAULT 0 CHECK (required IN (0, 1)),
            position INTEGER NOT NULL DEFAULT 0,
            created_by INTEGER NOT NULL REFERENCES users(id),
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            archived_at TEXT
        );

CREATE TABLE job_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job TEXT NOT NULL CHECK (job IN ('automations', 'backup')),
            status TEXT NOT NULL CHECK (status IN ('started', 'succeeded', 'failed')),
            detail TEXT,
            started_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            finished_at TEXT
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
        , read_at TEXT, grouped_key TEXT, deleted_at TEXT);

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
        , custom_values TEXT NOT NULL DEFAULT '{}', last_activity_at TEXT);

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

CREATE TABLE private_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            opportunity_id INTEGER NOT NULL REFERENCES opportunities(id),
            user_id INTEGER NOT NULL REFERENCES users(id),
            body TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            deleted_at TEXT
        );

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

CREATE TABLE sessions (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            expires_at TEXT NOT NULL
        );

CREATE TABLE task_assignees (
            task_id INTEGER NOT NULL REFERENCES tasks(id),
            user_id INTEGER NOT NULL REFERENCES users(id),
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            PRIMARY KEY (task_id, user_id)
        );

CREATE TABLE task_comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL REFERENCES tasks(id),
            body TEXT NOT NULL,
            created_by INTEGER NOT NULL REFERENCES users(id),
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            deleted_at TEXT
        );

CREATE TABLE task_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL REFERENCES tasks(id),
            version_number INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            assignee_id INTEGER REFERENCES users(id),
            due_date TEXT,
            edited_by INTEGER NOT NULL REFERENCES users(id),
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')), assignee_ids TEXT,
            UNIQUE (task_id, version_number)
        );

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
        , description TEXT NOT NULL DEFAULT '');

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
        , custom_values TEXT NOT NULL DEFAULT '{}', visibility TEXT NOT NULL DEFAULT 'shared'
            CHECK (visibility IN ('shared', 'private')));

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

CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        );

CREATE TABLE watchers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            opportunity_id INTEGER NOT NULL REFERENCES opportunities(id),
            user_id INTEGER NOT NULL REFERENCES users(id),
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            UNIQUE (opportunity_id, user_id)
        );

CREATE TRIGGER activity_comment_insert AFTER INSERT ON comments
        WHEN NEW.deleted_at IS NULL
        BEGIN
            UPDATE opportunities
            SET last_activity_at = MAX(
                COALESCE(last_activity_at, NEW.created_at), NEW.created_at
            )
            WHERE id = (
    SELECT opportunity_id FROM timeline_entries WHERE id = (
        SELECT entry_id FROM notes WHERE id = NEW.note_id
    )
);
        END;

CREATE TRIGGER activity_comment_update AFTER UPDATE ON comments
        BEGIN
            UPDATE opportunities
            SET last_activity_at = (
    SELECT MAX(activity_at) FROM (
        SELECT event_timestamp AS activity_at
        FROM timeline_entries
        WHERE opportunity_id = opportunities.id AND deleted_at IS NULL
        UNION ALL
        SELECT notes.created_at
        FROM notes
        JOIN timeline_entries ON timeline_entries.id = notes.entry_id
        WHERE timeline_entries.opportunity_id = opportunities.id
            AND notes.deleted_at IS NULL
            AND timeline_entries.deleted_at IS NULL
        UNION ALL
        SELECT comments.created_at
        FROM comments
        JOIN notes ON notes.id = comments.note_id
        JOIN timeline_entries ON timeline_entries.id = notes.entry_id
        WHERE timeline_entries.opportunity_id = opportunities.id
            AND comments.deleted_at IS NULL
            AND notes.deleted_at IS NULL
            AND timeline_entries.deleted_at IS NULL
    )
)
            WHERE id = (
    SELECT opportunity_id FROM timeline_entries WHERE id = (
        SELECT entry_id FROM notes WHERE id = NEW.note_id
    )
);
        END;

CREATE TRIGGER activity_entry_insert AFTER INSERT ON timeline_entries
        WHEN NEW.deleted_at IS NULL
        BEGIN
            UPDATE opportunities
            SET last_activity_at = MAX(
                COALESCE(last_activity_at, NEW.event_timestamp), NEW.event_timestamp
            )
            WHERE id = NEW.opportunity_id;
        END;

CREATE TRIGGER activity_entry_update AFTER UPDATE ON timeline_entries
        BEGIN
            UPDATE opportunities
            SET last_activity_at = (
    SELECT MAX(activity_at) FROM (
        SELECT event_timestamp AS activity_at
        FROM timeline_entries
        WHERE opportunity_id = NEW.opportunity_id AND deleted_at IS NULL
        UNION ALL
        SELECT notes.created_at
        FROM notes
        JOIN timeline_entries ON timeline_entries.id = notes.entry_id
        WHERE timeline_entries.opportunity_id = NEW.opportunity_id
            AND notes.deleted_at IS NULL
            AND timeline_entries.deleted_at IS NULL
        UNION ALL
        SELECT comments.created_at
        FROM comments
        JOIN notes ON notes.id = comments.note_id
        JOIN timeline_entries ON timeline_entries.id = notes.entry_id
        WHERE timeline_entries.opportunity_id = NEW.opportunity_id
            AND comments.deleted_at IS NULL
            AND notes.deleted_at IS NULL
            AND timeline_entries.deleted_at IS NULL
    )
)
            WHERE id = NEW.opportunity_id;
        END;

CREATE TRIGGER activity_note_insert AFTER INSERT ON notes
        WHEN NEW.deleted_at IS NULL
        BEGIN
            UPDATE opportunities
            SET last_activity_at = MAX(
                COALESCE(last_activity_at, NEW.created_at), NEW.created_at
            )
            WHERE id = (
                SELECT opportunity_id FROM timeline_entries WHERE id = NEW.entry_id
            );
        END;

CREATE TRIGGER activity_note_update AFTER UPDATE ON notes
        BEGIN
            UPDATE opportunities
            SET last_activity_at = (
    SELECT MAX(activity_at) FROM (
        SELECT event_timestamp AS activity_at
        FROM timeline_entries
        WHERE opportunity_id = opportunities.id AND deleted_at IS NULL
        UNION ALL
        SELECT notes.created_at
        FROM notes
        JOIN timeline_entries ON timeline_entries.id = notes.entry_id
        WHERE timeline_entries.opportunity_id = opportunities.id
            AND notes.deleted_at IS NULL
            AND timeline_entries.deleted_at IS NULL
        UNION ALL
        SELECT comments.created_at
        FROM comments
        JOIN notes ON notes.id = comments.note_id
        JOIN timeline_entries ON timeline_entries.id = notes.entry_id
        WHERE timeline_entries.opportunity_id = opportunities.id
            AND comments.deleted_at IS NULL
            AND notes.deleted_at IS NULL
            AND timeline_entries.deleted_at IS NULL
    )
)
            WHERE id = (
                SELECT opportunity_id FROM timeline_entries WHERE id = NEW.entry_id
            );
        END;

CREATE TRIGGER attachments_search_delete AFTER DELETE ON attachments BEGIN
                INSERT INTO search_index(search_index, rowid, title, body)
                SELECT 'delete', old.id * 8 + 3, old.filename, ''
                WHERE old.deleted_at IS NULL;
            END;

CREATE TRIGGER attachments_search_insert AFTER INSERT ON attachments BEGIN
                INSERT INTO search_index(rowid, title, body)
                SELECT new.id * 8 + 3, new.filename, ''
                WHERE new.deleted_at IS NULL;
            END;

CREATE TRIGGER attachments_search_update AFTER UPDATE ON attachments BEGIN
                INSERT INTO search_index(search_index, rowid, title, body)
                SELECT 'delete', old.id * 8 + 3, old.filename, ''
                WHERE old.deleted_at IS NULL;
                INSERT INTO search_index(rowid, title, body)
                SELECT new.id * 8 + 3, new.filename, ''
                WHERE new.deleted_at IS NULL;
            END;

CREATE TRIGGER comments_search_delete AFTER DELETE ON comments BEGIN
                INSERT INTO search_index(search_index, rowid, title, body)
                SELECT 'delete', old.id * 8 + 2, '', old.body
                WHERE old.deleted_at IS NULL;
            END;

CREATE TRIGGER comments_search_insert AFTER INSERT ON comments BEGIN
                INSERT INTO search_index(rowid, title, body)
                SELECT new.id * 8 + 2, '', new.body
                WHERE new.deleted_at IS NULL;
            END;

CREATE TRIGGER comments_search_update AFTER UPDATE ON comments BEGIN
                INSERT INTO search_index(search_index, rowid, title, body)
                SELECT 'delete', old.id * 8 + 2, '', old.body
                WHERE old.deleted_at IS NULL;
                INSERT INTO search_index(rowid, title, body)
                SELECT new.id * 8 + 2, '', new.body
                WHERE new.deleted_at IS NULL;
            END;

CREATE TRIGGER notes_search_delete AFTER DELETE ON notes BEGIN
                INSERT INTO search_index(search_index, rowid, title, body)
                SELECT 'delete', old.id * 8 + 1, '', old.body
                WHERE old.deleted_at IS NULL;
            END;

CREATE TRIGGER notes_search_insert AFTER INSERT ON notes BEGIN
                INSERT INTO search_index(rowid, title, body)
                SELECT new.id * 8 + 1, '', new.body
                WHERE new.deleted_at IS NULL;
            END;

CREATE TRIGGER notes_search_update AFTER UPDATE ON notes BEGIN
                INSERT INTO search_index(search_index, rowid, title, body)
                SELECT 'delete', old.id * 8 + 1, '', old.body
                WHERE old.deleted_at IS NULL;
                INSERT INTO search_index(rowid, title, body)
                SELECT new.id * 8 + 1, '', new.body
                WHERE new.deleted_at IS NULL;
            END;

CREATE TRIGGER timeline_entries_search_delete AFTER DELETE ON timeline_entries BEGIN
                INSERT INTO search_index(search_index, rowid, title, body)
                SELECT 'delete', old.id * 8 + 0, old.title, old.body
                WHERE old.deleted_at IS NULL;
            END;

CREATE TRIGGER timeline_entries_search_insert AFTER INSERT ON timeline_entries BEGIN
                INSERT INTO search_index(rowid, title, body)
                SELECT new.id * 8 + 0, new.title, new.body
                WHERE new.deleted_at IS NULL;
            END;

CREATE TRIGGER timeline_entries_search_update AFTER UPDATE ON timeline_entries BEGIN
                INSERT INTO search_index(search_index, rowid, title, body)
                SELECT 'delete', old.id * 8 + 0, old.title, old.body
                WHERE old.deleted_at IS NULL;
                INSERT INTO search_index(rowid, title, body)
                SELECT new.id * 8 + 0, new.title, new.body
                WHERE new.deleted_at IS NULL;
            END;
