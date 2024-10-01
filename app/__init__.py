from flask import Flask
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
import os

db = SQLAlchemy()
migrate = Migrate()

login_manager = LoginManager()
login_manager.login_view = 'login'

def create_app():
    app = Flask(__name__)
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'postgresql://postgres:mixasurg@localhost/OPD')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = os.getenv('SECRET_KEY', 'secretmegakey')
    SQLALCHEMY_ECHO = True	

    app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:mixasurg@localhost/OPD'
    app.config['SECRET_KEY'] = 'secret'
    login_manager.init_app(app)
    db.init_app(app)
    migrate.init_app(app, db)

    from .routes import main
    app.register_blueprint(main)

    return app

