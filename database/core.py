import sqlite3
from pathlib import Path

from flask import current_app, g

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL COLLATE NOCASE UNIQUE, email TEXT NOT NULL COLLATE NOCASE UNIQUE, password_hash TEXT NOT NULL, full_name TEXT NOT NULL, is_admin INTEGER NOT NULL DEFAULT 0 CHECK(is_admin IN (0,1)), is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS profiles (user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE, bio TEXT NOT NULL DEFAULT '', avatar_path TEXT, city TEXT NOT NULL DEFAULT '', learning_goal TEXT NOT NULL DEFAULT '', is_private INTEGER NOT NULL DEFAULT 0 CHECK(is_private IN (0,1)), updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS skills (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL COLLATE NOCASE UNIQUE, category TEXT NOT NULL DEFAULT '', description TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS user_skills (user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, skill_id INTEGER NOT NULL REFERENCES skills(id) ON DELETE CASCADE, skill_type TEXT NOT NULL CHECK(skill_type IN ('teach','learn')), level TEXT NOT NULL DEFAULT 'beginner' CHECK(level IN ('beginner','intermediate','advanced')), PRIMARY KEY(user_id,skill_id,skill_type));
CREATE TABLE IF NOT EXISTS posts (id INTEGER PRIMARY KEY AUTOINCREMENT, author_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, caption TEXT NOT NULL DEFAULT '', visibility TEXT NOT NULL DEFAULT 'public' CHECK(visibility IN ('public','friends')), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS post_attachments (id INTEGER PRIMARY KEY AUTOINCREMENT, post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE, file_path TEXT NOT NULL, file_name TEXT NOT NULL, file_type TEXT NOT NULL CHECK(file_type IN ('image','pdf','note')), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS post_skills (post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE, skill_id INTEGER NOT NULL REFERENCES skills(id) ON DELETE CASCADE, PRIMARY KEY(post_id,skill_id));
CREATE TABLE IF NOT EXISTS post_likes (post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(post_id,user_id));
CREATE TABLE IF NOT EXISTS comments (id INTEGER PRIMARY KEY AUTOINCREMENT, post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE, author_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, body TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS post_saves (post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(post_id,user_id));
CREATE TABLE IF NOT EXISTS friendships (id INTEGER PRIMARY KEY AUTOINCREMENT, requester_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, recipient_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','accepted')), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, responded_at TEXT, UNIQUE(requester_id,recipient_id), CHECK(requester_id <> recipient_id));
CREATE TABLE IF NOT EXISTS follows (follower_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, following_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(follower_id,following_id), CHECK(follower_id <> following_id));
CREATE TABLE IF NOT EXISTS rooms (id INTEGER PRIMARY KEY AUTOINCREMENT, owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, room_type TEXT NOT NULL CHECK(room_type IN ('personal','virtual')), title TEXT NOT NULL, slug TEXT NOT NULL UNIQUE, description TEXT NOT NULL DEFAULT '', is_open INTEGER NOT NULL DEFAULT 0 CHECK(is_open IN (0,1)), focus_minutes INTEGER NOT NULL DEFAULT 50 CHECK(focus_minutes BETWEEN 5 AND 180), break_minutes INTEGER NOT NULL DEFAULT 10 CHECK(break_minutes BETWEEN 1 AND 60), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE UNIQUE INDEX IF NOT EXISTS one_personal_room_per_owner ON rooms(owner_id) WHERE room_type='personal';
CREATE TABLE IF NOT EXISTS room_members (room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, role TEXT NOT NULL DEFAULT 'member' CHECK(role IN ('owner','member')), joined_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(room_id,user_id));
CREATE TABLE IF NOT EXISTS room_invites (id INTEGER PRIMARY KEY AUTOINCREMENT, room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE, inviter_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, invitee_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','accepted','rejected')), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(room_id,invitee_id));
CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, sender_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, recipient_id INTEGER REFERENCES users(id) ON DELETE CASCADE, room_id INTEGER REFERENCES rooms(id) ON DELETE CASCADE, body TEXT NOT NULL DEFAULT '', attachment_path TEXT, attachment_name TEXT, attachment_type TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, CHECK(recipient_id IS NOT NULL OR room_id IS NOT NULL));
CREATE TABLE IF NOT EXISTS message_reads (message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, read_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(message_id,user_id));
CREATE TABLE IF NOT EXISTS resources (id INTEGER PRIMARY KEY AUTOINCREMENT, uploader_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, room_id INTEGER REFERENCES rooms(id) ON DELETE SET NULL, title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', resource_type TEXT NOT NULL CHECK(resource_type IN ('pdf','note','image')), file_path TEXT NOT NULL, file_name TEXT NOT NULL, visibility TEXT NOT NULL DEFAULT 'public' CHECK(visibility IN ('public','room','private')), category TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS resource_skills (resource_id INTEGER NOT NULL REFERENCES resources(id) ON DELETE CASCADE, skill_id INTEGER NOT NULL REFERENCES skills(id) ON DELETE CASCADE, PRIMARY KEY(resource_id,skill_id));
CREATE TABLE IF NOT EXISTS bookmarks (user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, resource_id INTEGER NOT NULL REFERENCES resources(id) ON DELETE CASCADE, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(user_id,resource_id));
CREATE TABLE IF NOT EXISTS room_notes (id INTEGER PRIMARY KEY AUTOINCREMENT, room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE, author_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, title TEXT NOT NULL, body TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS whiteboard_strokes (id INTEGER PRIMARY KEY AUTOINCREMENT, room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE, author_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, stroke_json TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS study_presence (room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, activity TEXT NOT NULL DEFAULT 'studying' CHECK(activity IN ('studying','reading','writing','break')), last_seen TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(room_id,user_id));
CREATE TABLE IF NOT EXISTS typing_status (scope_type TEXT NOT NULL CHECK(scope_type IN ('room','direct')), scope_id TEXT NOT NULL, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, last_seen TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(scope_type,scope_id,user_id));
CREATE TABLE IF NOT EXISTS notifications (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, actor_id INTEGER REFERENCES users(id) ON DELETE SET NULL, notification_type TEXT NOT NULL, entity_type TEXT, entity_id INTEGER, message TEXT NOT NULL, is_read INTEGER NOT NULL DEFAULT 0 CHECK(is_read IN (0,1)), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS password_reset_tokens (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, token_hash TEXT NOT NULL UNIQUE, expires_at TEXT NOT NULL, used_at TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS ai_recommendations (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, recommendation_type TEXT NOT NULL CHECK(recommendation_type IN ('skill','friend','study','feed')), target_type TEXT NOT NULL, target_id INTEGER, title TEXT NOT NULL, explanation TEXT NOT NULL, score REAL NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS reports (id INTEGER PRIMARY KEY AUTOINCREMENT, reporter_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, target_type TEXT NOT NULL, target_id INTEGER NOT NULL, reason TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','reviewed','resolved')), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS audit_log (id INTEGER PRIMARY KEY AUTOINCREMENT, actor_id INTEGER REFERENCES users(id) ON DELETE SET NULL, action TEXT NOT NULL, target_type TEXT, target_id INTEGER, ip_address TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE INDEX IF NOT EXISTS idx_posts_created ON posts(created_at DESC); CREATE INDEX IF NOT EXISTS idx_notifications_user_read ON notifications(user_id,is_read,created_at DESC); CREATE INDEX IF NOT EXISTS idx_messages_room ON messages(room_id,created_at); CREATE INDEX IF NOT EXISTS idx_resources_visibility ON resources(visibility,created_at DESC);
"""

def get_db():
    if "db" not in g:
        path = Path(current_app.config["DATABASE_PATH"]); path.parent.mkdir(parents=True, exist_ok=True)
        g.db = sqlite3.connect(str(path)); g.db.row_factory = sqlite3.Row; g.db.execute("PRAGMA foreign_keys=ON")
    return g.db

def query(sql, params=(), one=False):
    cursor = get_db().execute(sql, params); rows = cursor.fetchall(); cursor.close()
    return (rows[0] if rows else None) if one else rows

def execute(sql, params=()):
    cursor = get_db().execute(sql, params); get_db().commit(); result = cursor.lastrowid; cursor.close(); return result

def execute_many(sql, values):
    get_db().executemany(sql, values); get_db().commit()

def close_db(_error=None):
    db = g.pop("db", None)
    if db: db.close()

def init_db():
    get_db().executescript(SCHEMA); get_db().commit()
print("DATABASE CORE LOADED - QUERY EXISTS")