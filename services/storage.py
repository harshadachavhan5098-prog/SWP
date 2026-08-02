import os
import uuid
from pathlib import Path

from flask import current_app
from PIL import Image, UnidentifiedImageError
from werkzeug.utils import secure_filename


def _extension(filename):
    return filename.rsplit(".", 1)[1].lower() if "." in filename else ""


def save_upload(upload, allowed_kind):
    if not upload or not upload.filename:
        return None
    extension = _extension(upload.filename)
    allowed = current_app.config["ALLOWED_IMAGE_EXTENSIONS"] if allowed_kind == "image" else current_app.config["ALLOWED_DOCUMENT_EXTENSIONS"]
    if extension not in allowed:
        raise ValueError("This file type is not allowed.")
    safe_name = secure_filename(upload.filename)
    if not safe_name:
        raise ValueError("Invalid file name.")
    if allowed_kind == "image":
        try:
            image = Image.open(upload.stream)
            image.verify()
            upload.stream.seek(0)
        except (UnidentifiedImageError, OSError):
            raise ValueError("The image file is invalid.")
    elif extension == "pdf":
        header = upload.stream.read(5)
        upload.stream.seek(0)
        if header != b"%PDF-":
            raise ValueError("The document is not a valid PDF.")
    stored_name = f"{uuid.uuid4().hex}.{extension}"
    destination = Path(current_app.config["UPLOAD_FOLDER"]) / stored_name
    upload.save(destination)
    return {"path": stored_name, "name": safe_name, "type": "image" if allowed_kind == "image" else ("pdf" if extension == "pdf" else "note")}


def delete_upload(stored_name):
    if stored_name:
        target = Path(current_app.config["UPLOAD_FOLDER"]) / Path(stored_name).name
        if target.exists():
            target.unlink()
