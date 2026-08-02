from flask_login import UserMixin
from database.core import query


class User(UserMixin):
    def __init__(self, row):
        self.id = row["id"]
        self.username = row["username"]
        self.email = row["email"]
        self.full_name = row["full_name"]
        self.is_admin = bool(row["is_admin"])
        self._active = bool(row["is_active"])

    @property
    def is_active(self):
        return self._active

    @classmethod
    def get_by_id(cls, user_id):
        row = query("SELECT * FROM users WHERE id = ?", (user_id,), one=True)
        return cls(row) if row else None

    @classmethod
    def get_by_identity(cls, identity):
        row = query("SELECT * FROM users WHERE email = ? OR username = ?", (identity, identity), one=True)
        return cls(row) if row else None
