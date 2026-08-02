from flask import Blueprint, abort, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from database.core import execute, query
from security import admin_required
from services.storage import delete_upload

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

@admin_bp.get("/")
@login_required
@admin_required
def dashboard():
    metrics = query("SELECT (SELECT COUNT(*) FROM users) AS users,(SELECT COUNT(*) FROM posts) AS posts,(SELECT COUNT(*) FROM rooms) AS rooms,(SELECT COUNT(*) FROM reports WHERE status='open') AS reports", one=True)
    users = query("SELECT u.*,p.avatar_path FROM users u JOIN profiles p ON p.user_id=u.id ORDER BY u.created_at DESC LIMIT 100")
    reports = query("SELECT r.*,u.username AS reporter_username FROM reports r JOIN users u ON u.id=r.reporter_id WHERE r.status='open' ORDER BY r.created_at DESC")
    return render_template("admin.html", metrics=metrics, users=users, reports=reports)

@admin_bp.post("/users/<int:user_id>/toggle")
@login_required
@admin_required
def toggle_user(user_id):
    if user_id == current_user.id: abort(400, "Administrators cannot disable themselves.")
    execute("UPDATE users SET is_active=CASE is_active WHEN 1 THEN 0 ELSE 1 END WHERE id=?", (user_id,))
    return redirect(url_for("admin.dashboard"))

@admin_bp.post("/reports/<int:report_id>/resolve")
@login_required
@admin_required
def resolve_report(report_id):
    execute("UPDATE reports SET status='resolved' WHERE id=?", (report_id,))
    return redirect(url_for("admin.dashboard"))

@admin_bp.post("/reports/<int:report_id>/remove-content")
@login_required
@admin_required
def remove_reported_content(report_id):
    report = query("SELECT * FROM reports WHERE id=?", (report_id,), one=True)
    if not report: abort(404)
    if report["target_type"] == "post":
        attachments = query("SELECT file_path FROM post_attachments WHERE post_id=?", (report["target_id"],))
        for attachment in attachments: delete_upload(attachment["file_path"])
        execute("DELETE FROM posts WHERE id=?", (report["target_id"],))
    elif report["target_type"] == "user": execute("UPDATE users SET is_active=0 WHERE id=?", (report["target_id"],))
    elif report["target_type"] == "room": execute("DELETE FROM rooms WHERE id=?", (report["target_id"],))
    elif report["target_type"] == "message": execute("DELETE FROM messages WHERE id=?", (report["target_id"],))
    else: abort(400)
    execute("UPDATE reports SET status='resolved' WHERE id=?", (report_id,))
    return redirect(url_for("admin.dashboard"))
