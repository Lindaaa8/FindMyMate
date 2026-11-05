"""SQLite persistence for FindYourMate (multi-user).

Tables
  users        one row per account (email/password and/or Facebook), profile stored as JSON
  connections  one row per pair attempt; user_a = who liked first, user_b = who was liked
  passes       "Not interested" marks (viewer -> target)
  messages     chat messages within a connection
  events       per-user activity log
"""
import copy
import json
import sqlite3
import threading
import time

from seed_data import CANDIDATES, NEW_PROFILE

SCHEMA_VERSION = 2

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE,
    password_hash TEXT,
    facebook_id TEXT UNIQUE,
    is_sample INTEGER NOT NULL DEFAULT 0,
    sample_key TEXT UNIQUE,
    created_at INTEGER NOT NULL,
    profile TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS connections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_a INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    user_b INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    state TEXT NOT NULL CHECK (state IN ('PENDING', 'CHATTING', 'DATING', 'ENGAGED', 'CLOSED')),
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    chatting_started_at INTEGER,
    a_confirmed INTEGER NOT NULL DEFAULT 0,
    b_confirmed INTEGER NOT NULL DEFAULT 0,
    engage_requested_by INTEGER
);
CREATE INDEX IF NOT EXISTS ix_conn_a ON connections(user_a, state);
CREATE INDEX IF NOT EXISTS ix_conn_b ON connections(user_b, state);
CREATE TABLE IF NOT EXISTS passes (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    target_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    at INTEGER NOT NULL,
    PRIMARY KEY (user_id, target_id)
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    connection_id INTEGER NOT NULL REFERENCES connections(id) ON DELETE CASCADE,
    sender_id INTEGER NOT NULL,
    text TEXT NOT NULL,
    at INTEGER NOT NULL,
    kind TEXT NOT NULL DEFAULT 'text',
    media_file TEXT,
    media_type TEXT,
    visible_to INTEGER          -- system notes shown to one person only (NULL = both)
);
CREATE TABLE IF NOT EXISTS password_resets (
    token_hash TEXT PRIMARY KEY,   -- sha256 of the emailed token (the token itself is never stored)
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS deletion_requests (
    code TEXT PRIMARY KEY,      -- confirmation code given to Facebook / the person
    at INTEGER NOT NULL,
    result TEXT NOT NULL        -- what was removed (no personal data)
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    at INTEGER NOT NULL,
    state TEXT NOT NULL,
    other_id INTEGER
);
"""

OLD_SINGLE_USER_TABLES = ["profile", "candidates", "connections", "messages", "events"]


def now_ms() -> int:
    return int(time.time() * 1000)


def sample_profile(c: dict) -> dict:
    """Turn a seeded candidate into a full profile row."""
    p = copy.deepcopy(NEW_PROFILE)
    for key in ["name", "bio", "education", "ethnicity", "nationality", "faith", "career", "location",
                "height", "hobbies", "hometown", "mbti", "gender", "photoVerified",
                "marriageStatus", "marriageVerified"]:
        p[key] = c[key]
    p["age"] = str(c["age"])
    p["skin"] = c.get("skin", "")
    p["color"] = c["color"]
    p["photos"] = [f"placeholder:{i}" for i in range(c["photoCount"])] + [None] * (9 - c["photoCount"])
    p["ideal"].update(c.get("ideal", {}))
    p["saved"] = p["confirmed"] = True
    return p


class Store:
    lock = threading.RLock()

    def __init__(self, path: str, seed_samples: bool = True):
        self.path = path
        with self.lock, self.connect() as db:
            self._migrate(db)
            self._allow_engaged_state(db)
            db.executescript(SCHEMA)
            db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            # Chat media columns (added after the first multi-user release).
            cols = {r[1] for r in db.execute("PRAGMA table_info(messages)")}
            for col, ddl in (("kind", "TEXT NOT NULL DEFAULT 'text'"), ("media_file", "TEXT"), ("media_type", "TEXT"),
                             ("visible_to", "INTEGER")):
                if col not in cols:
                    db.execute(f"ALTER TABLE messages ADD COLUMN {col} {ddl}")
            # Engagement now needs the partner's approval: who asked (NULL = no pending request).
            if "engage_requested_by" not in {r[1] for r in db.execute("PRAGMA table_info(connections)")}:
                db.execute("ALTER TABLE connections ADD COLUMN engage_requested_by INTEGER")
            # The "they liked you" state was renamed LIKED_BY_A -> FAVOURED; update old activity rows.
            db.execute("UPDATE events SET state = 'FAVOURED' WHERE state = 'LIKED_BY_A'")
            if seed_samples:
                self._seed_samples(db)

    def connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        return db

    # ---- setup -------------------------------------------------------------
    @staticmethod
    def _migrate(db):
        version = db.execute("PRAGMA user_version").fetchone()[0]
        has_old = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='profile'").fetchone()
        if version < SCHEMA_VERSION and has_old:
            # v1 was a single-user demo database with no accounts; start fresh.
            db.commit()
            db.execute("PRAGMA foreign_keys = OFF")
            for t in OLD_SINGLE_USER_TABLES:
                db.execute(f"DROP TABLE IF EXISTS {t}")
            db.commit()
            db.execute("PRAGMA foreign_keys = ON")

    @staticmethod
    def _allow_engaged_state(db):
        """Older databases restrict connections.state without 'ENGAGED'; rebuild that table if so."""
        row = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='connections'").fetchone()
        if not row or "ENGAGED" in row[0]:
            return
        db.commit()
        db.execute("PRAGMA foreign_keys = OFF")
        db.executescript("""
            CREATE TABLE connections_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_a INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                user_b INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                state TEXT NOT NULL CHECK (state IN ('PENDING', 'CHATTING', 'DATING', 'ENGAGED', 'CLOSED')),
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                chatting_started_at INTEGER,
                a_confirmed INTEGER NOT NULL DEFAULT 0,
                b_confirmed INTEGER NOT NULL DEFAULT 0
            );
            INSERT INTO connections_new SELECT id, user_a, user_b, state, created_at, updated_at,
                chatting_started_at, a_confirmed, b_confirmed FROM connections;
            DROP TABLE connections;
            ALTER TABLE connections_new RENAME TO connections;
        """)
        db.commit()
        db.execute("PRAGMA foreign_keys = ON")

    def _seed_samples(self, db):
        t = now_ms()
        for c in CANDIDATES:
            db.execute(
                "INSERT OR IGNORE INTO users (is_sample, sample_key, created_at, profile) VALUES (1, ?, ?, ?)",
                (c["id"], t, json.dumps(sample_profile(c))),
            )

    # ---- users -------------------------------------------------------------
    @staticmethod
    def _user(row) -> dict | None:
        if not row:
            return None
        profile = copy.deepcopy(NEW_PROFILE)
        stored = json.loads(row["profile"])
        profile.update({k: v for k, v in stored.items() if k != "ideal"})
        profile["ideal"].update(stored.get("ideal", {}))
        return {
            "id": row["id"], "email": row["email"], "facebook_id": row["facebook_id"],
            "password_hash": row["password_hash"], "is_sample": bool(row["is_sample"]),
            "created_at": row["created_at"], "profile": profile,
        }

    def user(self, uid: int) -> dict | None:
        with self.connect() as db:
            return self._user(db.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone())

    def user_by_email(self, email: str) -> dict | None:
        with self.connect() as db:
            return self._user(db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone())

    def user_by_facebook(self, fb_id: str) -> dict | None:
        with self.connect() as db:
            return self._user(db.execute("SELECT * FROM users WHERE facebook_id = ?", (fb_id,)).fetchone())

    def all_users(self) -> list[dict]:
        with self.connect() as db:
            return [self._user(r) for r in db.execute("SELECT * FROM users").fetchall()]

    def create_user(self, *, email=None, password_hash=None, facebook_id=None, profile=None) -> int:
        with self.lock, self.connect() as db:
            cur = db.execute(
                "INSERT INTO users (email, password_hash, facebook_id, created_at, profile) VALUES (?, ?, ?, ?, ?)",
                (email, password_hash, facebook_id, now_ms(), json.dumps(profile or NEW_PROFILE)),
            )
            return cur.lastrowid

    # ---- password reset ------------------------------------------------------
    def add_password_reset(self, token_hash: str, uid: int, ttl_ms: int):
        t = now_ms()
        with self.lock, self.connect() as db:
            db.execute("DELETE FROM password_resets WHERE expires_at < ?", (t,))
            db.execute("INSERT INTO password_resets (token_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
                       (token_hash, uid, t, t + ttl_ms))

    def password_reset(self, token_hash: str) -> dict | None:
        """The pending reset for this token, if it exists and hasn't expired."""
        with self.connect() as db:
            r = db.execute("SELECT * FROM password_resets WHERE token_hash = ? AND expires_at >= ?",
                           (token_hash, now_ms())).fetchone()
        return dict(r) if r else None

    def clear_password_resets(self, uid: int):
        with self.lock, self.connect() as db:
            db.execute("DELETE FROM password_resets WHERE user_id = ?", (uid,))

    def set_password_hash(self, uid: int, password_hash: str):
        with self.lock, self.connect() as db:
            db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, uid))

    def add_deletion_request(self, code: str, result: str):
        with self.lock, self.connect() as db:
            db.execute("INSERT INTO deletion_requests (code, at, result) VALUES (?, ?, ?)", (code, now_ms(), result))

    def deletion_request(self, code: str) -> dict | None:
        with self.connect() as db:
            r = db.execute("SELECT * FROM deletion_requests WHERE code = ?", (code,)).fetchone()
        return dict(r) if r else None

    def link_facebook(self, uid: int, fb_id: str | None):
        with self.lock, self.connect() as db:
            db.execute("UPDATE users SET facebook_id = ? WHERE id = ?", (fb_id, uid))

    def save_profile(self, uid: int, profile: dict):
        with self.lock, self.connect() as db:
            db.execute("UPDATE users SET profile = ? WHERE id = ?", (json.dumps(profile), uid))

    def delete_user(self, uid: int) -> list[str]:
        """Delete the account and its chats; returns chat media file names to remove from disk."""
        with self.lock, self.connect() as db:
            media = [r[0] for r in db.execute(
                "SELECT media_file FROM messages WHERE media_file IS NOT NULL AND connection_id IN "
                "(SELECT id FROM connections WHERE user_a = ? OR user_b = ?)", (uid, uid))]
            db.execute("DELETE FROM messages WHERE connection_id IN "
                       "(SELECT id FROM connections WHERE user_a = ? OR user_b = ?)", (uid, uid))
            db.execute("DELETE FROM users WHERE id = ?", (uid,))
        return media

    # ---- connections -------------------------------------------------------
    @staticmethod
    def _conn(row) -> dict | None:
        if not row:
            return None
        return {k: row[k] for k in row.keys()}

    def active_connection(self, uid: int) -> dict | None:
        """The user's accepted connection (CHATTING or DATING). Pending invitations don't count."""
        with self.connect() as db:
            return self._conn(db.execute(
                "SELECT * FROM connections WHERE (user_a = ? OR user_b = ?) AND state IN ('CHATTING', 'DATING', 'ENGAGED') "
                "ORDER BY updated_at DESC LIMIT 1", (uid, uid)).fetchone())

    def active_user_ids(self) -> set[int]:
        """Everyone currently locked into an accepted connection."""
        with self.connect() as db:
            rows = db.execute("SELECT user_a, user_b FROM connections WHERE state IN ('CHATTING', 'DATING', 'ENGAGED')").fetchall()
        return {r[0] for r in rows} | {r[1] for r in rows}

    def past_chats(self, uid: int) -> list[dict]:
        """Ended connections that had a chat, newest first, with message count and last message."""
        with self.connect() as db:
            rows = db.execute(
                "SELECT c.*, (SELECT COUNT(*) FROM messages m WHERE m.connection_id = c.id AND m.kind != 'system') AS message_count, "
                "(SELECT m.text FROM messages m WHERE m.connection_id = c.id AND m.kind != 'system' ORDER BY m.at DESC, m.id DESC LIMIT 1) AS last_text, "
                "(SELECT m.kind FROM messages m WHERE m.connection_id = c.id AND m.kind != 'system' ORDER BY m.at DESC, m.id DESC LIMIT 1) AS last_kind "
                "FROM connections c WHERE (c.user_a = ? OR c.user_b = ?) AND c.state = 'CLOSED' "
                "AND c.chatting_started_at IS NOT NULL ORDER BY c.updated_at DESC", (uid, uid)).fetchall()
        return [dict(r) for r in rows]

    def chats_started_before(self, cutoff_ms: int) -> list[dict]:
        """CHATTING connections whose chat started at or before `cutoff_ms`."""
        with self.connect() as db:
            rows = db.execute("SELECT * FROM connections WHERE state = 'CHATTING' AND chatting_started_at IS NOT NULL "
                              "AND chatting_started_at <= ?", (cutoff_ms,)).fetchall()
        return [self._conn(r) for r in rows]

    def pending_for(self, uid: int) -> list[dict]:
        """Open invitations the user sent (user_a) or received (user_b), newest first."""
        with self.connect() as db:
            rows = db.execute("SELECT * FROM connections WHERE (user_a = ? OR user_b = ?) AND state = 'PENDING' "
                              "ORDER BY updated_at DESC", (uid, uid)).fetchall()
        return [self._conn(r) for r in rows]

    def pending_between(self, a: int, b: int) -> dict | None:
        with self.connect() as db:
            return self._conn(db.execute(
                "SELECT * FROM connections WHERE state = 'PENDING' AND "
                "((user_a = ? AND user_b = ?) OR (user_a = ? AND user_b = ?)) ORDER BY id DESC LIMIT 1",
                (a, b, b, a)).fetchone())

    def connection(self, cid: int) -> dict | None:
        with self.connect() as db:
            return self._conn(db.execute("SELECT * FROM connections WHERE id = ?", (cid,)).fetchone())

    def connections_for(self, uid: int) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM connections WHERE user_a = ? OR user_b = ? ORDER BY updated_at DESC",
                              (uid, uid)).fetchall()
        return [self._conn(r) for r in rows]

    def create_connection(self, a: int, b: int) -> int:
        t = now_ms()
        with self.lock, self.connect() as db:
            cur = db.execute("INSERT INTO connections (user_a, user_b, state, created_at, updated_at) "
                             "VALUES (?, ?, 'PENDING', ?, ?)", (a, b, t, t))
            return cur.lastrowid

    def update_connection(self, cid: int, **fields):
        fields["updated_at"] = now_ms()
        cols = ", ".join(f"{k} = ?" for k in fields)
        with self.lock, self.connect() as db:
            db.execute(f"UPDATE connections SET {cols} WHERE id = ?", (*fields.values(), cid))

    # ---- passes ------------------------------------------------------------
    def passes(self, uid: int) -> set[int]:
        with self.connect() as db:
            return {r[0] for r in db.execute("SELECT target_id FROM passes WHERE user_id = ?", (uid,))}

    def add_pass(self, uid: int, target: int):
        with self.lock, self.connect() as db:
            db.execute("INSERT OR REPLACE INTO passes (user_id, target_id, at) VALUES (?, ?, ?)", (uid, target, now_ms()))

    def remove_pass(self, uid: int, target: int):
        with self.lock, self.connect() as db:
            db.execute("DELETE FROM passes WHERE user_id = ? AND target_id = ?", (uid, target))

    # ---- messages ----------------------------------------------------------
    def messages(self, conn_id: int, viewer: int | None = None) -> list[dict]:
        """Chat messages in order. System notes addressed to one person are only returned for that viewer."""
        with self.connect() as db:
            rows = db.execute("SELECT id, sender_id, text, at, kind, media_file, media_type FROM messages "
                              "WHERE connection_id = ? AND (visible_to IS NULL OR visible_to = ?) ORDER BY at, id",
                              (conn_id, viewer)).fetchall()
        return [dict(r) for r in rows]

    def add_system_message(self, conn_id: int, text: str, visible_to: int | None = None) -> int:
        """A note from the app inside the chat (e.g. engagement news); sender 0 = the app."""
        with self.lock, self.connect() as db:
            cur = db.execute("INSERT INTO messages (connection_id, sender_id, text, at, kind, visible_to) "
                             "VALUES (?, 0, ?, ?, 'system', ?)", (conn_id, text, now_ms(), visible_to))
            return cur.lastrowid

    def message(self, msg_id: int) -> dict | None:
        with self.connect() as db:
            r = db.execute("SELECT m.*, c.user_a, c.user_b FROM messages m JOIN connections c ON c.id = m.connection_id "
                           "WHERE m.id = ?", (msg_id,)).fetchone()
        return dict(r) if r else None

    def message_count(self, uid: int) -> int:
        with self.connect() as db:
            return db.execute("SELECT COUNT(*) FROM messages WHERE sender_id = ?", (uid,)).fetchone()[0]

    def add_message(self, conn_id: int, sender: int, text: str, kind: str = "text",
                    media_file: str | None = None, media_type: str | None = None) -> int:
        with self.lock, self.connect() as db:
            cur = db.execute("INSERT INTO messages (connection_id, sender_id, text, at, kind, media_file, media_type) "
                             "VALUES (?, ?, ?, ?, ?, ?, ?)", (conn_id, sender, text, now_ms(), kind, media_file, media_type))
            return cur.lastrowid

    # ---- events ------------------------------------------------------------
    def events(self, uid: int, limit: int = 100) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM events WHERE user_id = ? ORDER BY at DESC, id DESC LIMIT ?",
                              (uid, limit)).fetchall()
        return [{"id": r["id"], "text": r["text"], "at": r["at"], "state": r["state"], "otherId": r["other_id"]}
                for r in rows]

    def add_event(self, uid: int, text: str, state: str, other: int | None = None):
        with self.lock, self.connect() as db:
            db.execute("INSERT INTO events (user_id, text, at, state, other_id) VALUES (?, ?, ?, ?, ?)",
                       (uid, text, now_ms(), state, other))

    def clear_events(self, uid: int):
        with self.lock, self.connect() as db:
            db.execute("DELETE FROM events WHERE user_id = ?", (uid,))
