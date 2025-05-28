import os
from flask import Flask
from app.database import init_db
from app.routes import api  # ✅ Register the routes

def create_app():
    app = Flask(__name__)

    # Use an absolute path for the database file
    basedir = os.path.abspath(os.path.dirname(__file__))
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{os.path.join(basedir, '../instance/data.db')}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    init_db(app)

    # ✅ Register blueprint
    app.register_blueprint(api)

    return app
