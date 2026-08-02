import json
import secrets

from flask import Blueprint, abort, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from database.core import execute, query
from services.ai_service import room_chatbot_answer
from services.common import are_friends, clean_text, notify
from services.storage import save_upload

rooms_bp = Blueprint("rooms", __name__)


def room_for_user(room_id, allow_join=False):
    room = query("SELECT * FROM rooms WHERE id=?", (room_id,), one=True)
    if not room: abort(404)
    member = query("SELECT role FROM room_members WHERE room_id=? AND user_id=?", (room_id, current_user.id), one=True)
    if not member and not (allow_join and room["room_type"] == "virtual" and room["is_open"]): abort(403)
    return room, member


@rooms_bp.get("/my-room")
@login_required
def my_room():
    room = query("SELECT id FROM rooms WHERE owner_id=? AND room_type='personal'", (current_user.id,), one=True)
    return redirect(url_for("rooms.room", room_id=room["id"]))


@rooms_bp.route("/rooms/create-study", methods=["GET", "POST"])
@login_required
def create_study_room():
    if request.method == "POST":
        try:
            title = clean_text(request.form.get("title"), 80, 3)
            description = clean_text(request.form.get("description"), 300)
            focus = int(request.form.get("focus_minutes", 50)); pause = int(request.form.get("break_minutes", 10))
            if not 5 <= focus <= 180 or not 1 <= pause <= 60: raise ValueError("Choose valid Pomodoro durations.")
            room_id = execute("INSERT INTO rooms (owner_id,room_type,title,slug,description,is_open,focus_minutes,break_minutes) VALUES (?,?,?,?,?,1,?,?)", (current_user.id, "virtual", title, f"study-{secrets.token_hex(5)}", description, focus, pause))
            execute("INSERT INTO room_members (room_id,user_id,role) VALUES (?,?,'owner')", (room_id,current_user.id))
            return redirect(url_for("rooms.room", room_id=room_id))
        except (ValueError, TypeError) as error: return render_template("create_study_room.html", error=str(error))
    return render_template("create_study_room.html")


@rooms_bp.route("/rooms/<int:room_id>", methods=["GET"])
@login_required
def room(room_id):
    room_data, membership = room_for_user(room_id, allow_join=True)
    if not membership:
        return render_template("room_join.html", room=room_data)
    members = query("SELECT u.id,u.username,u.full_name,p.avatar_path,rm.role FROM room_members rm JOIN users u ON u.id=rm.user_id JOIN profiles p ON p.user_id=u.id WHERE rm.room_id=? ORDER BY rm.role DESC,u.full_name", (room_id,))
    friends = query("SELECT u.id,u.username,u.full_name FROM friendships f JOIN users u ON u.id=CASE WHEN f.requester_id=? THEN f.recipient_id ELSE f.requester_id END WHERE (f.requester_id=? OR f.recipient_id=?) AND f.status='accepted' AND NOT EXISTS(SELECT 1 FROM room_members rm WHERE rm.room_id=? AND rm.user_id=u.id) ORDER BY u.full_name", (current_user.id,current_user.id,current_user.id,room_id)) if room_data["room_type"] == "personal" and membership["role"] == "owner" else []
    notes = query("SELECT n.*,u.username FROM room_notes n JOIN users u ON u.id=n.author_id WHERE n.room_id=? ORDER BY n.updated_at DESC", (room_id,))
    resources = query("SELECT * FROM resources WHERE room_id=? ORDER BY created_at DESC", (room_id,))
    messages = query("SELECT m.*,u.username,u.full_name FROM messages m JOIN users u ON u.id=m.sender_id WHERE m.room_id=? ORDER BY m.created_at DESC LIMIT 100", (room_id,))
    presence = query("SELECT sp.*,u.username,u.full_name,p.avatar_path FROM study_presence sp JOIN users u ON u.id=sp.user_id JOIN profiles p ON p.user_id=u.id WHERE sp.room_id=? AND sp.last_seen > datetime('now','-2 minutes')", (room_id,))
    return render_template("room.html", room=room_data, membership=membership, members=members, friends=friends, notes=notes, resources=resources, messages=messages, presence=presence)


@rooms_bp.post("/rooms/<int:room_id>/join")
@login_required
def join_room(room_id):
    room_data, _ = room_for_user(room_id, allow_join=True)
    if room_data["room_type"] != "virtual" or not room_data["is_open"]: abort(403)
    execute("INSERT OR IGNORE INTO room_members (room_id,user_id) VALUES (?,?)", (room_id,current_user.id))
    return redirect(url_for("rooms.room", room_id=room_id))


@rooms_bp.post("/rooms/<int:room_id>/leave")
@login_required
def leave_room(room_id):
    room_data, membership = room_for_user(room_id)
    if membership["role"] == "owner": abort(400, "Room owners cannot leave their own room.")
    execute("DELETE FROM room_members WHERE room_id=? AND user_id=?", (room_id,current_user.id))
    return redirect(url_for("main.home"))


@rooms_bp.post("/rooms/<int:room_id>/invite")
@login_required
def invite(room_id):
    room_data, membership = room_for_user(room_id)
    if room_data["room_type"] != "personal" or membership["role"] != "owner": abort(403)
    invitee_id = int(request.form.get("user_id", 0))
    if not are_friends(current_user.id, invitee_id): abort(403)
    invite_id = execute("INSERT OR REPLACE INTO room_invites (room_id,inviter_id,invitee_id,status) VALUES (?,?,?,'pending')", (room_id,current_user.id,invitee_id))
    notify(invitee_id, "room_invite", f"{current_user.username} invited you to a private learning room.", current_user.id, "room_invite", invite_id)
    return redirect(url_for("rooms.room", room_id=room_id))


@rooms_bp.post("/rooms/invites/<int:invite_id>/<action>")
@login_required
def respond_invite(invite_id, action):
    invite = query("SELECT * FROM room_invites WHERE id=? AND invitee_id=? AND status='pending'", (invite_id,current_user.id), one=True)
    if not invite or action not in {"accept","reject"}: abort(403)
    if action == "accept":
        execute("UPDATE room_invites SET status='accepted' WHERE id=?", (invite_id,)); execute("INSERT OR IGNORE INTO room_members (room_id,user_id) VALUES (?,?)", (invite["room_id"],current_user.id))
    else: execute("UPDATE room_invites SET status='rejected' WHERE id=?", (invite_id,))
    return redirect(url_for("main.notifications"))


@rooms_bp.post("/rooms/<int:room_id>/members/<int:user_id>/remove")
@login_required
def remove_member(room_id, user_id):
    room_data, membership = room_for_user(room_id)
    if room_data["room_type"] != "personal" or membership["role"] != "owner" or user_id == current_user.id: abort(403)
    execute("DELETE FROM room_members WHERE room_id=? AND user_id=?", (room_id,user_id))
    return redirect(url_for("rooms.room", room_id=room_id))


@rooms_bp.post("/rooms/<int:room_id>/settings")
@login_required
def room_settings(room_id):
    room_data, membership = room_for_user(room_id)
    if membership["role"] != "owner": abort(403)
    try:
        title = clean_text(request.form.get("title"), 80, 3)
        description = clean_text(request.form.get("description"), 300)
        if room_data["room_type"] == "virtual":
            focus, pause = int(request.form.get("focus_minutes", 50)), int(request.form.get("break_minutes", 10))
            if not 5 <= focus <= 180 or not 1 <= pause <= 60: raise ValueError("Invalid Pomodoro settings.")
            execute("UPDATE rooms SET title=?,description=?,focus_minutes=?,break_minutes=? WHERE id=?", (title,description,focus,pause,room_id))
        else: execute("UPDATE rooms SET title=?,description=? WHERE id=?", (title,description,room_id))
    except (ValueError, TypeError) as error: abort(400,str(error))
    return redirect(url_for("rooms.room", room_id=room_id))


@rooms_bp.post("/rooms/<int:room_id>/messages")
@login_required
def send_room_message(room_id):
    room_for_user(room_id)
    body = clean_text(request.form.get("body"), 2000)
    attachment = save_upload(request.files.get("attachment"), "document")
    if not body and not attachment: abort(400, "Write a message or attach a file.")
    message_id = execute("INSERT INTO messages (sender_id,room_id,body,attachment_path,attachment_name,attachment_type) VALUES (?,?,?,?,?,?)", (current_user.id,room_id,body,attachment["path"] if attachment else None,attachment["name"] if attachment else None,attachment["type"] if attachment else None))
    return jsonify({"id":message_id,"body":body,"username":current_user.username})


@rooms_bp.get("/rooms/<int:room_id>/messages")
@login_required
def room_messages(room_id):
    room_for_user(room_id)
    messages = query("SELECT m.*,u.username FROM messages m JOIN users u ON u.id=m.sender_id WHERE m.room_id=? ORDER BY m.created_at DESC LIMIT 100", (room_id,))
    return jsonify([dict(row) for row in messages])


@rooms_bp.post("/rooms/<int:room_id>/notes")
@login_required
def save_note(room_id):
    room_for_user(room_id)
    try:
        title = clean_text(request.form.get("title"), 120, 1); body = clean_text(request.form.get("body"), 20000, 1)
        note_id = execute("INSERT INTO room_notes (room_id,author_id,title,body) VALUES (?,?,?,?)", (room_id,current_user.id,title,body))
        return jsonify({"id":note_id,"title":title,"body":body})
    except ValueError as error: abort(400,str(error))


@rooms_bp.put("/rooms/<int:room_id>/notes/<int:note_id>")
@login_required
def edit_note(room_id, note_id):
    room_for_user(room_id)
    note = query("SELECT author_id FROM room_notes WHERE id=? AND room_id=?", (note_id,room_id), one=True)
    if not note or note["author_id"] != current_user.id: abort(403)
    data = request.get_json(silent=True) or {}
    execute("UPDATE room_notes SET title=?,body=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", (clean_text(data.get("title"),120,1),clean_text(data.get("body"),20000,1),note_id))
    return jsonify({"ok":True})


@rooms_bp.post("/rooms/<int:room_id>/whiteboard")
@login_required
def save_stroke(room_id):
    room_for_user(room_id)
    data = request.get_json(silent=True) or {}; stroke = data.get("stroke")
    if not isinstance(stroke, dict) or len(json.dumps(stroke)) > 20000: abort(400, "Invalid drawing data.")
    stroke_id = execute("INSERT INTO whiteboard_strokes (room_id,author_id,stroke_json) VALUES (?,?,?)", (room_id,current_user.id,json.dumps(stroke)))
    return jsonify({"id":stroke_id})


@rooms_bp.get("/rooms/<int:room_id>/whiteboard")
@login_required
def get_strokes(room_id):
    room_for_user(room_id)
    strokes = query("SELECT id,stroke_json FROM whiteboard_strokes WHERE room_id=? ORDER BY id", (room_id,))
    return jsonify([{"id":row["id"],"stroke":json.loads(row["stroke_json"])} for row in strokes])


@rooms_bp.post("/rooms/<int:room_id>/presence")
@login_required
def update_presence(room_id):
    room_data, _ = room_for_user(room_id)
    if room_data["room_type"] != "virtual": abort(400)
    activity = request.form.get("activity", "studying")
    if activity not in {"studying","reading","writing","break"}: abort(400)
    execute("INSERT INTO study_presence (room_id,user_id,activity,last_seen) VALUES (?,?,?,CURRENT_TIMESTAMP) ON CONFLICT(room_id,user_id) DO UPDATE SET activity=excluded.activity,last_seen=CURRENT_TIMESTAMP", (room_id,current_user.id,activity))
    return jsonify({"ok":True})


@rooms_bp.post("/rooms/<int:room_id>/resources")
@login_required
def add_resource(room_id):
    room_for_user(room_id)
    try:
        upload = request.files.get("file"); extension = upload.filename.rsplit(".",1)[-1].lower() if upload and "." in upload.filename else ""
        entry = save_upload(upload, "image" if extension in {"png","jpg","jpeg","webp"} else "document")
        title = clean_text(request.form.get("title") or entry["name"], 160, 1)
        resource_id = execute("INSERT INTO resources (uploader_id,room_id,title,description,resource_type,file_path,file_name,visibility,category) VALUES (?,?,?,?,?,?,?,?,?)", (current_user.id,room_id,title,clean_text(request.form.get("description"),1000),entry["type"],entry["path"],entry["name"],"room",clean_text(request.form.get("category"),60)))
        return jsonify({"id":resource_id,"title":title})
    except ValueError as error: abort(400,str(error))


@rooms_bp.post("/rooms/<int:room_id>/ai")
@login_required
def room_ai(room_id):
    data = request.get_json(silent=True) or {}
    try: return jsonify(room_chatbot_answer(current_user.id,room_id,data.get("question")))
    except PermissionError: abort(403)
    except ValueError as error: abort(400,str(error))
