import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from database.core import query


def _user_skill_text(user_id):
    rows = query("SELECT s.name FROM user_skills us JOIN skills s ON s.id=us.skill_id WHERE us.user_id=?", (user_id,))
    return " ".join(row["name"] for row in rows)


def recommendations_for(user_id):
    interest_text = _user_skill_text(user_id)
    data = {"skills": [], "people": [], "resources": [], "posts": []}
    skills = query("SELECT s.id,s.name,s.description FROM skills s WHERE NOT EXISTS(SELECT 1 FROM user_skills us WHERE us.user_id=? AND us.skill_id=s.id) ORDER BY s.name", (user_id,))
    if skills:
        corpus = [interest_text] + [f"{row['name']} {row['description']}" for row in skills]
        scores = cosine_similarity(TfidfVectorizer(stop_words="english").fit_transform(corpus))[0][1:]
        data["skills"] = [{"id": row["id"], "name": row["name"], "score": round(float(score), 3)} for row, score in zip(skills, scores) if score > 0][:6]
    people = query("SELECT u.id,u.username,u.full_name,GROUP_CONCAT(s.name, ' ') AS skill_text FROM users u LEFT JOIN user_skills us ON us.user_id=u.id LEFT JOIN skills s ON s.id=us.skill_id WHERE u.id<>? AND u.is_active=1 AND NOT EXISTS(SELECT 1 FROM friendships f WHERE (f.requester_id=? AND f.recipient_id=u.id) OR (f.recipient_id=? AND f.requester_id=u.id)) GROUP BY u.id", (user_id,user_id,user_id))
    if people and interest_text:
        scores = cosine_similarity(TfidfVectorizer(stop_words="english").fit_transform([interest_text] + [(row["skill_text"] or "") for row in people]))[0][1:]
        data["people"] = [{"id": row["id"], "username": row["username"], "full_name": row["full_name"], "score": round(float(score), 3)} for row, score in zip(people, scores) if score > 0][:6]
    resources = query("SELECT r.id,r.title,r.description,r.category FROM resources r WHERE r.visibility='public' ORDER BY r.created_at DESC LIMIT 100")
    if resources and interest_text:
        scores = cosine_similarity(TfidfVectorizer(stop_words="english").fit_transform([interest_text] + [f"{row['title']} {row['description']} {row['category']}" for row in resources]))[0][1:]
        data["resources"] = [{"id": row["id"], "title": row["title"], "score": round(float(score), 3)} for row, score in zip(resources, scores) if score > 0][:6]
    posts = query("SELECT p.id,p.caption,u.username,GROUP_CONCAT(s.name, ' ') AS skills FROM posts p JOIN users u ON u.id=p.author_id LEFT JOIN post_skills ps ON ps.post_id=p.id LEFT JOIN skills s ON s.id=ps.skill_id WHERE p.visibility='public' GROUP BY p.id ORDER BY p.created_at DESC LIMIT 100")
    if posts and interest_text:
        scores = cosine_similarity(TfidfVectorizer(stop_words="english").fit_transform([interest_text] + [f"{row['caption']} {row['skills'] or ''}" for row in posts]))[0][1:]
        data["posts"] = [{"id": row["id"], "caption": row["caption"], "username": row["username"], "score": round(float(score), 3)} for row, score in zip(posts, scores) if score > 0][:8]
    return data


def room_chatbot_answer(user_id, room_id, question):
    question = (question or "").strip()
    if not question or len(question) > 800:
        raise ValueError("Ask a focused question of up to 800 characters.")
    is_member = query("SELECT 1 FROM room_members WHERE room_id=? AND user_id=?", (room_id, user_id), one=True)
    if not is_member:
        raise PermissionError("You do not have access to this room.")
    resources = query("SELECT title,description FROM resources WHERE room_id=?", (room_id,))
    notes = query("SELECT title,body FROM room_notes WHERE room_id=?", (room_id,))
    sources = [(row["title"], row["description"]) for row in resources] + [(row["title"], row["body"]) for row in notes]
    if not sources:
        return {"answer": "This room has no shared notes or resources yet. Add a PDF or note, then I can ground study guidance in your room material.", "source": None}
    texts = [f"{title} {body}" for title, body in sources]
    matrix = TfidfVectorizer(stop_words="english").fit_transform([question] + texts)
    scores = cosine_similarity(matrix[0:1], matrix[1:]).ravel()
    index = int(np.argmax(scores))
    title, text = sources[index]
    excerpt = " ".join(text.split())[:700]
    return {"answer": f"From {title}: {excerpt}", "source": title, "score": round(float(scores[index]), 3)}
