from pathlib import Path

from flask import Blueprint, abort, current_app, jsonify, redirect, render_template, request, send_from_directory, url_for
from flask_login import current_user, login_required

from database.core import execute, query
from services.common import are_friends

main_bp = Blueprint("main", __name__)


@main_bp.get("/")
@login_required
def home():
    posts = query("""SELECT p.*, u.username, u.full_name, pr.avatar_path,
        (SELECT COUNT(*) FROM post_likes l WHERE l.post_id=p.id) AS like_count,
        (SELECT COUNT(*) FROM comments c WHERE c.post_id=p.id) AS comment_count,
        EXISTS(SELECT 1 FROM post_likes l WHERE l.post_id=p.id AND l.user_id=?) AS liked,
        EXISTS(SELECT 1 FROM post_saves s WHERE s.post_id=p.id AND s.user_id=?) AS saved
        FROM posts p JOIN users u ON u.id=p.author_id JOIN profiles pr ON pr.user_id=u.id
        WHERE p.visibility='public' OR p.author_id=? OR EXISTS(SELECT 1 FROM friendships f WHERE f.status='accepted' AND ((f.requester_id=? AND f.recipient_id=p.author_id) OR (f.recipient_id=? AND f.requester_id=p.author_id)))
        ORDER BY p.created_at DESC LIMIT 40""", (current_user.id, current_user.id, current_user.id, current_user.id, current_user.id))
    feed = []
    for post in posts:
        item = dict(post)
        item["attachments"] = query("SELECT * FROM post_attachments WHERE post_id=? ORDER BY id", (post["id"],))
        item["skills"] = query("SELECT s.name FROM post_skills ps JOIN skills s ON s.id=ps.skill_id WHERE ps.post_id=?", (post["id"],))
        item["comments"] = query("SELECT c.*,u.username FROM comments c JOIN users u ON u.id=c.author_id WHERE c.post_id=? ORDER BY c.created_at DESC LIMIT 3", (post["id"],))
        feed.append(item)
    rooms = query("SELECT r.*, (SELECT COUNT(*) FROM study_presence sp WHERE sp.room_id=r.id AND sp.last_seen > datetime('now','-2 minutes')) AS active_count FROM rooms r WHERE r.room_type='virtual' AND r.is_open=1 ORDER BY r.created_at DESC LIMIT 8")
    return render_template("home.html", posts=feed, rooms=rooms)


@main_bp.get("/search")
@login_required
def search():
    term = request.args.get("q", "").strip()
    results = {"users": [], "skills": [], "posts": [], "rooms": [], "resources": []}
    if term:
        pattern = f"%{term}%"
        results["users"] = query("SELECT u.username,u.full_name,pr.avatar_path FROM users u JOIN profiles pr ON pr.user_id=u.id WHERE u.is_active=1 AND (u.username LIKE ? OR u.full_name LIKE ?) LIMIT 12", (pattern, pattern))
        results["skills"] = query("SELECT * FROM skills WHERE name LIKE ? OR category LIKE ? LIMIT 16", (pattern, pattern))
        results["posts"] = query("SELECT p.id,p.caption,u.username FROM posts p JOIN users u ON u.id=p.author_id WHERE p.visibility='public' AND p.caption LIKE ? ORDER BY p.created_at DESC LIMIT 12", (pattern,))
        results["rooms"] = query("SELECT * FROM rooms WHERE room_type='virtual' AND is_open=1 AND (title LIKE ? OR description LIKE ?) LIMIT 12", (pattern, pattern))
        results["resources"] = query("SELECT r.*,u.username FROM resources r JOIN users u ON u.id=r.uploader_id WHERE r.visibility='public' AND (r.title LIKE ? OR r.description LIKE ? OR r.category LIKE ?) LIMIT 12", (pattern, pattern, pattern))
    return render_template("search.html", term=term, results=results)


@main_bp.get("/notifications")
@login_required
def notifications():
    rows = query("SELECT n.*, u.username AS actor_username, u.full_name AS actor_name FROM notifications n LEFT JOIN users u ON u.id=n.actor_id WHERE n.user_id=? ORDER BY n.created_at DESC LIMIT 100", (current_user.id,))
    return render_template("notifications.html", notifications=rows)


@main_bp.post("/notifications/read-all")
@login_required
def read_notifications():
    execute("UPDATE notifications SET is_read=1 WHERE user_id=?", (current_user.id,))
    return redirect(url_for("main.notifications"))


@main_bp.get("/library")
@login_required
def library():
    category = request.args.get("category", "").strip()
    sql = "SELECT r.*,u.username,EXISTS(SELECT 1 FROM bookmarks b WHERE b.resource_id=r.id AND b.user_id=?) AS bookmarked FROM resources r JOIN users u ON u.id=r.uploader_id WHERE (r.visibility='public' OR r.uploader_id=?)"
    params = [current_user.id, current_user.id]
    if category:
        sql += " AND r.category=?"; params.append(category)
    sql += " ORDER BY r.created_at DESC LIMIT 80"
    resources = query(sql, tuple(params))
    categories = query("SELECT DISTINCT category FROM resources WHERE visibility='public' AND category<>'' ORDER BY category")
    return render_template("library.html", resources=resources, categories=categories, current_category=category)


def _attachment_access(kind, item_id):
    if kind == "avatar":
        row = query("SELECT p.avatar_path,u.id FROM profiles p JOIN users u ON u.id=p.user_id WHERE u.id=?", (item_id,), one=True)
        if not row or not row["avatar_path"]: abort(404)
        return row["avatar_path"]
    if kind == "post":
        row = query("SELECT a.file_path,p.author_id,p.visibility FROM post_attachments a JOIN posts p ON p.id=a.post_id WHERE a.id=?", (item_id,), one=True)
        if not row: abort(404)
        if row["visibility"] == "friends" and row["author_id"] != current_user.id and not are_friends(row["author_id"], current_user.id): abort(403)
        return row["file_path"]
    if kind == "resource":
        row = query("SELECT r.file_path,r.uploader_id,r.visibility,r.room_id FROM resources r WHERE r.id=?", (item_id,), one=True)
        if not row: abort(404)
        allowed = row["visibility"] == "public" or row["uploader_id"] == current_user.id
        if row["visibility"] == "room":
            allowed = bool(query("SELECT 1 FROM room_members WHERE room_id=? AND user_id=?", (row["room_id"], current_user.id), one=True))
        if not allowed: abort(403)
        return row["file_path"]
    if kind == "message":
        row = query("SELECT attachment_path,sender_id,recipient_id,room_id FROM messages WHERE id=?", (item_id,), one=True)
        if not row or not row["attachment_path"]: abort(404)
        allowed = current_user.id in (row["sender_id"], row["recipient_id"])
        if row["room_id"]: allowed = bool(query("SELECT 1 FROM room_members WHERE room_id=? AND user_id=?", (row["room_id"], current_user.id), one=True))
        if not allowed: abort(403)
        return row["attachment_path"]
    abort(404)


@main_bp.get("/media/<kind>/<int:item_id>")
@login_required
def media(kind, item_id):
    stored_name = _attachment_access(kind, item_id)
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], Path(stored_name).name, as_attachment=False)


@main_bp.get("/api/unread-count")
@login_required
def unread_count():
    row = query("SELECT COUNT(*) AS total FROM notifications WHERE user_id=? AND is_read=0", (current_user.id,), one=True)
    return jsonify({"count": row["total"]})
