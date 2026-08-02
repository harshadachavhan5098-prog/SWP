import re
from datetime import datetime

from database.core import execute, query

USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{3,30}$")


def clean_text(value, maximum, minimum=0):
    value = (value or "").strip()
    if len(value) < minimum or len(value) > maximum:
        raise ValueError(f"Text must contain between {minimum} and {maximum} characters.")
    return value


def valid_username(username):
    return bool(USERNAME_RE.fullmatch(username or ""))


def skill_ids_from_names(names):
    ids = []
    for name in {part.strip()[:50] for part in (names or "").split(",") if part.strip()}:
        row = query("SELECT id FROM skills WHERE name = ?", (name,), one=True)
        ids.append(row["id"] if row else execute("INSERT INTO skills (name) VALUES (?)", (name,)))
    return ids


def notify(user_id, notification_type, message, actor_id=None, entity_type=None, entity_id=None):
    return execute("INSERT INTO notifications (user_id,actor_id,notification_type,entity_type,entity_id,message) VALUES (?,?,?,?,?,?)", (user_id, actor_id, notification_type, entity_type, entity_id, message))


def friendship_status(first_id, second_id):
    return query("SELECT * FROM friendships WHERE (requester_id=? AND recipient_id=?) OR (requester_id=? AND recipient_id=?)", (first_id, second_id, second_id, first_id), one=True)


def are_friends(first_id, second_id):
    row = friendship_status(first_id, second_id)
    return bool(row and row["status"] == "accepted")


def now_iso():
    return datetime.utcnow().replace(microsecond=0).isoformat(sep=" ")
