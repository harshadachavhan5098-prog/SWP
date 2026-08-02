from flask import Flask
from flask_login import LoginManager

from config import Config
from database.core import close_db, init_db
from security import install_security

login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Please sign in to continue."
login_manager.login_message_category = "info"


def create_app(config_class=Config):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)
    app.config.from_pyfile("config.py", silent=True)
    config_class.validate()
    login_manager.init_app(app)
    app.teardown_appcontext(close_db)
    install_security(app)

    from models.user import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.get_by_id(user_id)

    from routes.auth import auth_bp
    from routes.main import main_bp
    from routes.social import social_bp
    from routes.rooms import rooms_bp
    from routes.admin import admin_bp
    for blueprint in (auth_bp, main_bp, social_bp, rooms_bp, admin_bp):
        app.register_blueprint(blueprint)

    with app.app_context():
        init_db()
    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=app.config["PORT"], debug=app.config["DEBUG"])
