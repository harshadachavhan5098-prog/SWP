from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from database.core import execute, query
from services.common import are_friends, clean_text, friendship_status, notify, skill_ids_from_names
from services.storage import save_upload
from services.ai_service import recommendations_for

social_bp = Blueprint("social", __name__)


def _post_or_404(post_id):
    row = query("SELECT * FROM posts WHERE id=?", (post_id,), one=True)
    if not row: abort(404)
    if row["visibility"] == "friends" and row["author_id"] != current_user.id and not are_friends(row["author_id"], current_user.id): abort(403)
    return row


@social_bp.route("/posts/create", methods=["GET", "POST"])
@login_required
def create_post():
    if request.method == "POST":
        try:
            caption = clean_text(request.form.get("caption"), 2200)
            visibility = request.form.get("visibility", "public")
            if visibility not in {"public", "friends"}: raise ValueError("Invalid visibility.")
            files = [item for item in request.files.getlist("attachments") if item and item.filename]
            if not caption and not files: raise ValueError("Add a caption or an educational attachment.")
            if len(files) > 4: raise ValueError("A post supports up to four attachments.")
            post_id = execute("INSERT INTO posts (author_id,caption,visibility) VALUES (?,?,?)", (current_user.id, caption, visibility))
            for upload in files:
                extension = upload.filename.rsplit(".", 1)[-1].lower() if "." in upload.filename else ""
                entry = save_upload(upload, "image" if extension in {"png", "jpg", "jpeg", "webp"} else "document")
                execute("INSERT INTO post_attachments (post_id,file_path,file_name,file_type) VALUES (?,?,?,?)", (post_id, entry["path"], entry["name"], entry["type"]))
            execute_many = [(post_id, skill_id) for skill_id in skill_ids_from_names(request.form.get("skills", ""))]
            if execute_many:
                from database.core import execute_many as write_many
                write_many("INSERT OR IGNORE INTO post_skills (post_id,skill_id) VALUES (?,?)", execute_many)
            return redirect(url_for("main.home"))
        except ValueError as error: flash(str(error), "error")
    return render_template("create_post.html")


@social_bp.post("/posts/<int:post_id>/like")
@login_required
def toggle_like(post_id):
    post = _post_or_404(post_id)
    existing = query("SELECT 1 FROM post_likes WHERE post_id=? AND user_id=?", (post_id, current_user.id), one=True)
    if existing:
        execute("DELETE FROM post_likes WHERE post_id=? AND user_id=?", (post_id, current_user.id)); liked = False
    else:
        execute("INSERT INTO post_likes (post_id,user_id) VALUES (?,?)", (post_id, current_user.id)); liked = True
        if post["author_id"] != current_user.id: notify(post["author_id"], "like", f"{current_user.username} liked your post.", current_user.id, "post", post_id)
    count = query("SELECT COUNT(*) AS total FROM post_likes WHERE post_id=?", (post_id,), one=True)["total"]
    return jsonify({"liked": liked, "count": count}) if request.accept_mimetypes.best == "application/json" else redirect(request.referrer or url_for("main.home"))


@social_bp.post("/posts/<int:post_id>/comments")
@login_required
def add_comment(post_id):
    post = _post_or_404(post_id)
    try:
        body = clean_text(request.form.get("body"), 800, 1)
        comment_id = execute("INSERT INTO comments (post_id,author_id,body) VALUES (?,?,?)", (post_id, current_user.id, body))
        if post["author_id"] != current_user.id: notify(post["author_id"], "comment", f"{current_user.username} commented on your post.", current_user.id, "post", post_id)
        return jsonify({"id": comment_id, "body": body, "username": current_user.username}) if request.accept_mimetypes.best == "application/json" else redirect(request.referrer or url_for("main.home"))
    except ValueError as error: abort(400, str(error))


@social_bp.post("/posts/<int:post_id>/save")
@login_required
def toggle_save(post_id):
    _post_or_404(post_id)
    exists = query("SELECT 1 FROM post_saves WHERE post_id=? AND user_id=?", (post_id, current_user.id), one=True)
    if exists: execute("DELETE FROM post_saves WHERE post_id=? AND user_id=?", (post_id, current_user.id)); saved = False
    else: execute("INSERT INTO post_saves (post_id,user_id) VALUES (?,?)", (post_id, current_user.id)); saved = True
    return jsonify({"saved": saved})


@social_bp.route("/u/<username>", methods=["GET", "POST"])
@login_required
def profile(username):
    user = query("SELECT u.*,p.bio,p.avatar_path,p.city,p.learning_goal,p.is_private FROM users u JOIN profiles p ON p.user_id=u.id WHERE u.username=? AND u.is_active=1", (username,), one=True)
    if not user: abort(404)
    is_owner = user["id"] == current_user.id
    relationship = friendship_status(current_user.id, user["id"]) if not is_owner else None
    is_following = bool(query("SELECT 1 FROM follows WHERE follower_id=? AND following_id=?", (current_user.id, user["id"]), one=True)) if not is_owner else False
    can_view = is_owner or not user["is_private"] or are_friends(current_user.id, user["id"])
    if not can_view: return render_template("profile.html", user=user, private_profile=True, relationship=relationship, is_following=is_following, is_owner=False)
    if request.method == "POST":
        if not is_owner: abort(403)
        try:
            bio = clean_text(request.form.get("bio"), 500)
            city = clean_text(request.form.get("city"), 80)
            goal = clean_text(request.form.get("learning_goal"), 160)
            avatar = save_upload(request.files.get("avatar"), "image")
            if avatar: execute("UPDATE profiles SET bio=?,city=?,learning_goal=?,is_private=?,avatar_path=?,updated_at=CURRENT_TIMESTAMP WHERE user_id=?", (bio, city, goal, int(bool(request.form.get("is_private"))), avatar["path"], current_user.id))
            else: execute("UPDATE profiles SET bio=?,city=?,learning_goal=?,is_private=?,updated_at=CURRENT_TIMESTAMP WHERE user_id=?", (bio, city, goal, int(bool(request.form.get("is_private"))), current_user.id))
            return redirect(url_for("social.profile", username=current_user.username))
        except ValueError as error: flash(str(error), "error")
    skills = query("SELECT s.*,us.skill_type,us.level FROM user_skills us JOIN skills s ON s.id=us.skill_id WHERE us.user_id=? ORDER BY us.skill_type,s.name", (user["id"],))
    posts = query("SELECT p.*, (SELECT COUNT(*) FROM post_likes l WHERE l.post_id=p.id) AS like_count FROM posts p WHERE p.author_id=? ORDER BY p.created_at DESC", (user["id"],))
    saved = query("SELECT p.* FROM post_saves ps JOIN posts p ON p.id=ps.post_id WHERE ps.user_id=? ORDER BY ps.created_at DESC", (user["id"],)) if is_owner else []
    stats = query("SELECT (SELECT COUNT(*) FROM friendships WHERE status='accepted' AND (requester_id=? OR recipient_id=?)) AS friends, (SELECT COUNT(*) FROM posts WHERE author_id=?) AS posts, (SELECT COUNT(*) FROM follows WHERE following_id=?) AS followers, (SELECT COUNT(*) FROM follows WHERE follower_id=?) AS following", (user["id"], user["id"], user["id"], user["id"], user["id"]), one=True)
    return render_template("profile.html", user=user, skills=skills, posts=posts, saved=saved, stats=stats, relationship=relationship, is_following=is_following, is_owner=is_owner, private_profile=False)


@social_bp.post("/profile/skills")
@login_required
def update_skills():
    skill_type = request.form.get("skill_type")
    level = request.form.get("level", "beginner")
    if skill_type not in {"teach", "learn"} or level not in {"beginner", "intermediate", "advanced"}: abort(400)
    names = skill_ids_from_names(request.form.get("skills", ""))
    for skill_id in names: execute("INSERT OR REPLACE INTO user_skills (user_id,skill_id,skill_type,level) VALUES (?,?,?,?)", (current_user.id, skill_id, skill_type, level))
    return redirect(url_for("social.profile", username=current_user.username))


@social_bp.post("/friends/<int:user_id>/request")
@login_required
def request_friend(user_id):
    print("\n========== FRIEND REQUEST ==========")
    print("Current User ID:", current_user.id)
    print("Target User ID :", user_id)

    if user_id == current_user.id:
        print("Cannot send request to self")
        abort(404)

    user = query(
        "SELECT id FROM users WHERE id=? AND is_active=1",
        (user_id,),
        one=True,
    )

    print("Target user exists:", user)

    if not user:
        print("User not found")
        abort(404)

    existing = friendship_status(current_user.id, user_id)
    print("Existing friendship:", existing)

    if not existing:
        try:
            friendship_id = execute(
                "INSERT INTO friendships (requester_id, recipient_id) VALUES (?, ?)",
                (current_user.id, user_id),
            )

            print("Friendship inserted:", friendship_id)

            notify(
                user_id,
                "friend_request",
                f"{current_user.username} sent you a friend request.",
                current_user.id,
                "friendship",
                friendship_id,
            )

            print("Notification sent")

        except Exception as e:
            print("DATABASE ERROR:", e)
            raise

    print("========== END ==========\n")

    return redirect(request.referrer or url_for("main.search"))


@social_bp.post("/follow/<int:user_id>")
@login_required
def toggle_follow(user_id):
    if user_id == current_user.id or not query("SELECT id FROM users WHERE id=? AND is_active=1", (user_id,), one=True): abort(404)
    existing = query("SELECT 1 FROM follows WHERE follower_id=? AND following_id=?", (current_user.id,user_id), one=True)
    if existing:
        execute("DELETE FROM follows WHERE follower_id=? AND following_id=?", (current_user.id,user_id))
    else:
        execute("INSERT INTO follows (follower_id,following_id) VALUES (?,?)", (current_user.id,user_id))
        notify(user_id, "follow", f"{current_user.username} started following your learning journey.", current_user.id, "user", current_user.id)
    return redirect(request.referrer or url_for("main.home"))


@social_bp.post("/friends/<int:friendship_id>/<action>")
@login_required
def respond_friend(friendship_id, action):
    friendship = query("SELECT * FROM friendships WHERE id=?", (friendship_id,), one=True)
    if not friendship or (friendship["recipient_id"] != current_user.id and action in {"accept", "reject"}): abort(403)
    if action == "accept":
        execute("UPDATE friendships SET status='accepted',responded_at=CURRENT_TIMESTAMP WHERE id=?", (friendship_id,)); notify(friendship["requester_id"], "friend_accepted", f"{current_user.username} accepted your request.", current_user.id, "friendship", friendship_id)
    elif action == "reject": execute("DELETE FROM friendships WHERE id=?", (friendship_id,))
    elif action == "remove" and current_user.id in (friendship["requester_id"], friendship["recipient_id"]): execute("DELETE FROM friendships WHERE id=?", (friendship_id,))
    else: abort(400)
    return redirect(request.referrer or url_for("social.friends"))


@social_bp.get("/friends")
@login_required
def friends():
    incoming = query("SELECT f.*,u.username,u.full_name FROM friendships f JOIN users u ON u.id=f.requester_id WHERE f.recipient_id=? AND f.status='pending'", (current_user.id,))
    accepted = query("SELECT f.id,u.id AS user_id,u.username,u.full_name,p.avatar_path FROM friendships f JOIN users u ON u.id=CASE WHEN f.requester_id=? THEN f.recipient_id ELSE f.requester_id END JOIN profiles p ON p.user_id=u.id WHERE (f.requester_id=? OR f.recipient_id=?) AND f.status='accepted'", (current_user.id, current_user.id, current_user.id))
    suggestions = query("SELECT u.id,u.username,u.full_name,COUNT(us.skill_id) AS overlap FROM users u JOIN user_skills us ON us.user_id=u.id WHERE u.id<>? AND u.is_active=1 AND us.skill_id IN (SELECT skill_id FROM user_skills WHERE user_id=?) AND NOT EXISTS(SELECT 1 FROM friendships f WHERE (f.requester_id=? AND f.recipient_id=u.id) OR (f.recipient_id=? AND f.requester_id=u.id)) GROUP BY u.id ORDER BY overlap DESC,u.created_at DESC LIMIT 12", (current_user.id,current_user.id,current_user.id,current_user.id))
    return render_template("friends.html", incoming=incoming, accepted=accepted, suggestions=suggestions)


@social_bp.route("/messages/<username>", methods=["GET", "POST"])
@login_required
def direct_messages(username):
    recipient = query("SELECT u.id,u.username,u.full_name,p.avatar_path FROM users u JOIN profiles p ON p.user_id=u.id WHERE u.username=? AND u.is_active=1", (username,), one=True)
    if not recipient: abort(404)
    if recipient["id"] == current_user.id or not are_friends(current_user.id, recipient["id"]): abort(403)
    if request.method == "POST":
        try:
            body = clean_text(request.form.get("body"), 2000)
            upload = request.files.get("attachment")
            entry = None
            if upload and upload.filename:
                extension = upload.filename.rsplit(".", 1)[-1].lower() if "." in upload.filename else ""
                entry = save_upload(upload, "image" if extension in {"png","jpg","jpeg","webp"} else "document")
            if not body and not entry: raise ValueError("Write a message or attach a file.")
            message_id = execute("INSERT INTO messages (sender_id,recipient_id,body,attachment_path,attachment_name,attachment_type) VALUES (?,?,?,?,?,?)", (current_user.id,recipient["id"],body,entry["path"] if entry else None,entry["name"] if entry else None,entry["type"] if entry else None))
            notify(recipient["id"], "message", f"{current_user.username} sent you a private message.", current_user.id, "message", message_id)
            if request.accept_mimetypes.best == "application/json":
                return jsonify({"id": message_id, "body": body, "attachment_name": entry["name"] if entry else None})
        except ValueError as error: flash(str(error), "error")
        return redirect(url_for("social.direct_messages", username=username))
    messages = query("SELECT m.*,u.username FROM messages m JOIN users u ON u.id=m.sender_id WHERE ((m.sender_id=? AND m.recipient_id=?) OR (m.sender_id=? AND m.recipient_id=?)) ORDER BY m.created_at ASC", (current_user.id,recipient["id"],recipient["id"],current_user.id))
    execute("INSERT OR IGNORE INTO message_reads (message_id,user_id) SELECT id,? FROM messages WHERE sender_id=? AND recipient_id=?", (current_user.id,recipient["id"],current_user.id))
    return render_template("messages.html", recipient=recipient, messages=messages)


@social_bp.get("/messages/<username>/data")
@login_required
def direct_messages_data(username):
    recipient = query("SELECT id FROM users WHERE username=? AND is_active=1", (username,), one=True)
    if not recipient or not are_friends(current_user.id, recipient["id"]): abort(403)
    rows = query("SELECT m.*,u.username FROM messages m JOIN users u ON u.id=m.sender_id WHERE ((m.sender_id=? AND m.recipient_id=?) OR (m.sender_id=? AND m.recipient_id=?)) ORDER BY m.created_at ASC", (current_user.id,recipient["id"],recipient["id"],current_user.id))
    return jsonify([dict(row) for row in rows])


@social_bp.post("/messages/<username>/typing")
@login_required
def direct_typing(username):
    recipient = query("SELECT id FROM users WHERE username=?", (username,), one=True)
    if not recipient or not are_friends(current_user.id, recipient["id"]): abort(403)
    pair_key = "-".join(map(str, sorted((current_user.id, recipient["id"]))))
    execute("INSERT INTO typing_status (scope_type,scope_id,user_id,last_seen) VALUES ('direct',?,?,CURRENT_TIMESTAMP) ON CONFLICT(scope_type,scope_id,user_id) DO UPDATE SET last_seen=CURRENT_TIMESTAMP", (pair_key,current_user.id))
    return jsonify({"ok":True})


@social_bp.get("/messages/<username>/typing")
@login_required
def direct_typing_status(username):
    recipient = query("SELECT id FROM users WHERE username=?", (username,), one=True)
    if not recipient or not are_friends(current_user.id, recipient["id"]): abort(403)
    pair_key = "-".join(map(str, sorted((current_user.id, recipient["id"]))))
    active = query("SELECT 1 FROM typing_status WHERE scope_type='direct' AND scope_id=? AND user_id=? AND last_seen > datetime('now','-5 seconds')", (pair_key,recipient["id"]), one=True)
    return jsonify({"typing":bool(active)})


@social_bp.route("/library/upload", methods=["GET", "POST"])
@login_required
def upload_resource():
    if request.method == "POST":
        try:
            upload = request.files.get("file")
            extension = upload.filename.rsplit(".", 1)[-1].lower() if upload and "." in upload.filename else ""
            entry = save_upload(upload, "image" if extension in {"png","jpg","jpeg","webp"} else "document")
            title = clean_text(request.form.get("title") or entry["name"], 160, 1)
            visibility = request.form.get("visibility", "public")
            if visibility not in {"public", "private"}: raise ValueError("Invalid resource visibility.")
            resource_id = execute("INSERT INTO resources (uploader_id,title,description,resource_type,file_path,file_name,visibility,category) VALUES (?,?,?,?,?,?,?,?)", (current_user.id,title,clean_text(request.form.get("description"),1000),entry["type"],entry["path"],entry["name"],visibility,clean_text(request.form.get("category"),60)))
            skill_pairs = [(resource_id,skill_id) for skill_id in skill_ids_from_names(request.form.get("skills", ""))]
            if skill_pairs:
                from database.core import execute_many
                execute_many("INSERT OR IGNORE INTO resource_skills (resource_id,skill_id) VALUES (?,?)", skill_pairs)
            return redirect(url_for("main.library"))
        except ValueError as error: flash(str(error), "error")
    return render_template("upload_resource.html")


@social_bp.post("/resources/<int:resource_id>/bookmark")
@login_required
def bookmark(resource_id):
    resource = query("SELECT id,visibility,uploader_id FROM resources WHERE id=?", (resource_id,), one=True)
    if not resource or (resource["visibility"] == "private" and resource["uploader_id"] != current_user.id): abort(404)
    existing = query("SELECT 1 FROM bookmarks WHERE user_id=? AND resource_id=?", (current_user.id,resource_id), one=True)
    if existing: execute("DELETE FROM bookmarks WHERE user_id=? AND resource_id=?", (current_user.id,resource_id)); bookmarked=False
    else: execute("INSERT INTO bookmarks (user_id,resource_id) VALUES (?,?)", (current_user.id,resource_id)); bookmarked=True
    return jsonify({"bookmarked":bookmarked})


@social_bp.post("/reports")
@login_required
def report():
    target_type = request.form.get("target_type")
    target_id = request.form.get("target_id", type=int)
    if target_type not in {"post","user","room","message"} or not target_id: abort(400)
    reason = clean_text(request.form.get("reason"), 500, 4)
    execute("INSERT INTO reports (reporter_id,target_type,target_id,reason) VALUES (?,?,?,?)", (current_user.id,target_type,target_id,reason))
    flash("Thanks. The report was sent to the moderation team.", "success")
    return redirect(request.referrer or url_for("main.home"))


@social_bp.get("/recommendations")
@login_required
def recommendations():
    return render_template("recommendations.html", recommendations=recommendations_for(current_user.id))
