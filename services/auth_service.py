import secrets
from datetime import datetime, timedelta

from flask import current_app
from werkzeug.security import check_password_hash, generate_password_hash

from database.core import execute, query
from security import hash_token
from services.common import valid_username
from services.mailer import send_password_reset


def validate_password(password):
    if len(password or "") < 12 or not any(char.isupper() for char in password) or not any(char.islower() for char in password) or not any(char.isdigit() for char in password):
        raise ValueError("Use at least 12 characters including uppercase, lowercase, and a number.")


def register_user(full_name, username, email, password):
    full_name, username, email = full_name.strip(), username.strip(), email.strip().lower()
    if not 2 <= len(full_name) <= 80 or not valid_username(username) or "@" not in email or len(email) > 254:
        raise ValueError("Enter a valid name, username, and email address.")
    validate_password(password)
    if query("SELECT id FROM users WHERE username=? OR email=?", (username, email), one=True):
        raise ValueError("That username or email is already registered.")
    is_admin = int(email in current_app.config["ADMIN_EMAILS"])
    user_id = execute("INSERT INTO users (username,email,password_hash,full_name,is_admin) VALUES (?,?,?,?,?)", (username, email, generate_password_hash(password), full_name, is_admin))
    execute("INSERT INTO profiles (user_id) VALUES (?)", (user_id,))
    slug = f"{username}-{secrets.token_hex(4)}"
    room_id = execute("INSERT INTO rooms (owner_id,room_type,title,slug,description) VALUES (?,?,?,?,?)", (user_id, "personal", f"{full_name}'s Learning Room", slug, "A private space for focused skill exchange."))
    execute("INSERT INTO room_members (room_id,user_id,role) VALUES (?,?,'owner')", (room_id, user_id))
    return user_id


def authenticate(identity, password):
    user = query("SELECT * FROM users WHERE (email=? OR username=?) AND is_active=1", (identity.strip().lower(), identity.strip()), one=True)
    return user if user and check_password_hash(user["password_hash"], password) else None


def start_password_reset(email, reset_url_builder):
    user = query("SELECT id,email FROM users WHERE email=? AND is_active=1", (email.strip().lower(),), one=True)
    if not user:
        return
    raw_token = secrets.token_urlsafe(32)
    expires = datetime.utcnow() + timedelta(minutes=current_app.config["PASSWORD_RESET_TTL_MINUTES"])
    execute("DELETE FROM password_reset_tokens WHERE user_id=? OR expires_at < CURRENT_TIMESTAMP", (user["id"],))
    execute(
    "INSERT INTO password_reset_tokens (user_id,token_hash,expires_at) VALUES (?,?,?)",
    (user["id"], hash_token(raw_token), expires.isoformat(sep=" "))
)
    send_password_reset(user["email"], reset_url_builder(raw_token))


def consume_password_reset(raw_token, password):
    validate_password(password)
    token = query("SELECT * FROM password_reset_tokens WHERE token_hash=? AND used_at IS NULL AND expires_at > CURRENT_TIMESTAMP", (hash_token(raw_token),), one=True)
    if not token:
        raise ValueError("This reset link is invalid or has expired.")
    execute("UPDATE users SET password_hash=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (generate_password_hash(password), token["user_id"]))
    execute("UPDATE password_reset_tokens SET used_at=CURRENT_TIMESTAMP WHERE id=?", (token["id"],))