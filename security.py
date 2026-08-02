import hashlib
import secrets
from functools import wraps
from flask import abort, request, session
from flask_login import current_user

def csrf_token():
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32); session["csrf_token"] = token
    return token

def validate_csrf():
    value = request.form.get("csrf_token") or request.headers.get("X-CSRFToken")
    if not value or not session.get("csrf_token") or not secrets.compare_digest(value, session["csrf_token"]): abort(400, "Invalid CSRF token.")

def hash_token(token): return hashlib.sha256(token.encode("utf-8")).hexdigest()

def admin_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin: abort(403)
        return view(*args, **kwargs)
    return wrapper

def install_security(app):
    @app.context_processor
    def security_context(): return {"csrf_token": csrf_token}
    @app.before_request
    def protect_mutations():
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and not request.path.startswith("/static/"): validate_csrf()
    @app.after_request
    def headers(response):
        response.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'self'"
        response.headers["X-Content-Type-Options"] = "nosniff"; response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"; response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response
