"""SQLite persistence; connections never cross threads or network calls."""
import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


def stamp():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class Store:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS rules(id TEXT PRIMARY KEY, kind TEXT NOT NULL,
                    pattern TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
                    UNIQUE(kind, pattern));
                CREATE TABLE IF NOT EXISTS comments(id TEXT PRIMARY KEY, owner TEXT NOT NULL,
                    video_id TEXT NOT NULL, parent_id TEXT NOT NULL DEFAULT '',
                    author TEXT NOT NULL, author_id TEXT NOT NULL, text TEXT NOT NULL,
                    published TEXT NOT NULL, seen TEXT NOT NULL, reasons TEXT NOT NULL,
                    moderation TEXT NOT NULL DEFAULT 'published', last_action TEXT NOT NULL DEFAULT '');
                CREATE INDEX IF NOT EXISTS comments_owner ON comments(owner, published DESC);
                CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, kind TEXT NOT NULL,
                    state TEXT NOT NULL, created TEXT NOT NULL, finished TEXT,
                    progress TEXT NOT NULL DEFAULT '{}', error TEXT NOT NULL DEFAULT '');
                CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT, at TEXT NOT NULL, level TEXT NOT NULL, message TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS actions(id TEXT PRIMARY KEY, job_id TEXT NOT NULL,
                    comment_id TEXT NOT NULL, action TEXT NOT NULL, state TEXT NOT NULL,
                    at TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '');
            """)
            db.execute("UPDATE jobs SET state='interrupted',finished=?,error='Application stopped before completion.' WHERE state IN ('queued','running')", (stamp(),))
            db.execute("UPDATE actions SET state='unknown',detail='Interrupted: verify on YouTube before retrying.' WHERE state='submitted'")

    @contextmanager
    def connect(self):
        with self.lock:
            db = sqlite3.connect(self.path, timeout=10)
            db.row_factory = sqlite3.Row
            try:
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise
            finally:
                db.close()

    def setting(self, key, default=None):
        with self.connect() as db:
            row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            return json.loads(row[0]) if row else default

    def set_setting(self, key, value):
        with self.connect() as db:
            db.execute("INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, json.dumps(value)))

    def rules(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT * FROM rules ORDER BY rowid")]

    def add_rule(self, kind, pattern, enabled=True):
        key = uuid.uuid4().hex
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO rules VALUES(?,?,?,?)", (key, kind, pattern.strip(), int(enabled)))

    def delete_rule(self, key):
        with self.connect() as db:
            db.execute("DELETE FROM rules WHERE id=?", (key,))

    def reclassify(self, book):
        with self.connect() as db:
            for row in db.execute("SELECT id,text,author_id FROM comments").fetchall():
                db.execute("UPDATE comments SET reasons=? WHERE id=?", (json.dumps(book.match(row['text'], row['author_id'])), row['id']))

    def replace_rules(self, rules):
        from .rules import RuleBook
        book = RuleBook(rules)
        with self.connect() as db:
            # Classification and the rule edit commit together, including regex failures.
            updates = [(json.dumps(book.match(row['text'], row['author_id'])), row['id'])
                       for row in db.execute('SELECT id,text,author_id FROM comments').fetchall()]
            db.execute('DELETE FROM rules')
            db.executemany('INSERT INTO rules VALUES(?,?,?,?)',
                           [(r['id'],r['kind'],r['pattern'],int(r.get('enabled', True))) for r in rules])
            db.executemany('UPDATE comments SET reasons=? WHERE id=?', updates)

    def save_comment(self, comment, reasons):
        with self.connect() as db:
            db.execute("""INSERT INTO comments(id,owner,video_id,parent_id,author,author_id,text,published,seen,reasons,moderation)
                VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                last_action=CASE WHEN comments.text!=excluded.text THEN '' ELSE comments.last_action END,
                text=excluded.text,author=excluded.author,seen=excluded.seen,reasons=excluded.reasons,
                moderation=excluded.moderation""",
                tuple(comment[k] for k in ('id','owner','video_id','parent_id','author','author_id','text','published')) +
                (stamp(), json.dumps(reasons), comment.get('moderation', 'published')))

    def comments(self, owner, view="all", search="", offset=0, limit=50):
        clauses, values = ["owner=?"], [owner]
        if view == "flagged":
            clauses += ["reasons!='[]'", "last_action=''", "moderation!='rejected'"]
        elif view == "handled":
            clauses += ["last_action!=''"]
        if search:
            clauses.append("(instr(lower(text),lower(?))>0 OR instr(lower(author),lower(?))>0)")
            values += [search, search]
        where = " AND ".join(clauses)
        with self.connect() as db:
            total = db.execute(f"SELECT COUNT(*) FROM comments WHERE {where}", values).fetchone()[0]
            rows = db.execute(f"SELECT * FROM comments WHERE {where} ORDER BY published DESC,id LIMIT ? OFFSET ?", values + [limit, offset]).fetchall()
            return {"total": total, "items": [dict(r) | {"reasons": json.loads(r['reasons'])} for r in rows]}

    def selected(self, ids, owner):
        if not ids:
            return []
        with self.connect() as db:
            return [dict(r) for r in db.execute(f"SELECT * FROM comments WHERE owner=? AND id IN ({','.join('?' for _ in ids)})", [owner] + ids)]

    def stats(self, owner):
        with self.connect() as db:
            row = db.execute("""SELECT COUNT(*) total,
                SUM(CASE WHEN reasons!='[]' AND last_action='' AND moderation!='rejected' THEN 1 ELSE 0 END) flagged,
                SUM(CASE WHEN last_action!='' THEN 1 ELSE 0 END) handled FROM comments WHERE owner=?""", (owner,)).fetchone()
            return {k: row[k] or 0 for k in ('total','flagged','handled')}

    def create_job(self, kind):
        key = uuid.uuid4().hex
        with self.connect() as db:
            db.execute("INSERT INTO jobs(id,kind,state,created) VALUES(?,?,'queued',?)", (key, kind, stamp()))
        return key

    def update_job(self, key, state=None, progress=None, error=""):
        with self.connect() as db:
            if progress is not None:
                db.execute("UPDATE jobs SET progress=? WHERE id=?", (json.dumps(progress), key))
            if state:
                end = stamp() if state not in {'queued','running'} else None
                db.execute("UPDATE jobs SET state=?,finished=?,error=? WHERE id=?", (state, end, error, key))

    def jobs(self, limit=30):
        with self.connect() as db:
            return [dict(r) | {"progress": json.loads(r['progress'])} for r in db.execute("SELECT * FROM jobs ORDER BY rowid DESC LIMIT ?", (limit,))]

    def event(self, job, message, level="info"):
        with self.connect() as db:
            db.execute("INSERT INTO events(job_id,at,level,message) VALUES(?,?,?,?)", (job, stamp(), level, message[:2000]))

    def events(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT * FROM events ORDER BY id DESC LIMIT 150")]

    def begin_action(self, job, comment_id, action):
        key = uuid.uuid4().hex
        with self.connect() as db:
            db.execute("INSERT INTO actions VALUES(?,?,?,?,?,?,?)", (key, job, comment_id, action, 'submitted', stamp(), ''))
        return key

    def finish_action(self, key, state, detail=""):
        with self.connect() as db:
            db.execute("UPDATE actions SET state=?,detail=? WHERE id=?", (state, detail[:1500], key))
            if state == 'confirmed':
                row = db.execute("SELECT comment_id,action FROM actions WHERE id=?", (key,)).fetchone()
                moderation = {'hold':'heldForReview','reject':'rejected','ban':'rejected','publish':'published'}[row['action']]
                db.execute("UPDATE comments SET last_action=?,moderation=? WHERE id=?", (row['action'], moderation, row['comment_id']))

    def uncertain(self, comment_id):
        with self.connect() as db:
            return bool(db.execute("SELECT 1 FROM actions WHERE comment_id=? AND state IN ('submitted','unknown') LIMIT 1", (comment_id,)).fetchone())

    def actions(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT * FROM actions ORDER BY rowid DESC LIMIT 200")]
