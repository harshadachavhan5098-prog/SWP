from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_user, logout_user

from models.user import User
from services.auth_service import authenticate, consume_password_reset, register_user, start_password_reset

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated: return redirect(url_for("main.home"))
    if request.method == "POST":
        row = authenticate(request.form.get("identity", ""), request.form.get("password", ""))
        if row:
            session.permanent = True
            login_user(User(row), remember=bool(request.form.get("remember")))
            return redirect(request.args.get("next") or url_for("main.home"))
        flash("Invalid sign-in details.", "error")
    return render_template("login.html")

@auth_bp.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user.is_authenticated: return redirect(url_for("main.home"))
    if request.method == "POST":
        try:
            register_user(request.form.get("full_name", ""), request.form.get("username", ""), request.form.get("email", ""), request.form.get("password", ""))
            flash("Your SWP account is ready. Please sign in.", "success")
            return redirect(url_for("auth.login"))
        except ValueError as error: flash(str(error), "error")
    return render_template("signup.html")

@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        start_password_reset(request.form.get("email", ""), lambda token: url_for("auth.reset_password", token=token, _external=True))
        flash("If that account exists, a password-reset message has been sent.", "success")
        return redirect(url_for("auth.login"))
    return render_template("forgot_password.html")

@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    if request.method == "POST":
        try:
            consume_password_reset(token, request.form.get("password", ""))
            flash("Your password was updated. Please sign in.", "success")
            return redirect(url_for("auth.login"))
        except ValueError as error: flash(str(error), "error")
    return render_template("reset_password.html", token=token)

@auth_bp.post("/logout")
def logout():
    logout_user(); flash("You have been signed out.", "info")
    return redirect(url_for("auth.login"))
