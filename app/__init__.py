import hmac
import os
import time
from datetime import timedelta

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
from werkzeug.exceptions import HTTPException

load_dotenv()
db = SQLAlchemy()


def _db_url():
    url = os.getenv("DATABASE_URL", "postgresql+psycopg2://postgres:postgres@localhost:5432/inventory")
    if url.startswith("postgres://"):  # Heroku/Render style
        url = url.replace("postgres://", "postgresql+psycopg2://", 1)
    return url


def _init_db():
    """Create tables once, even when several workers boot at the same time."""
    if db.engine.dialect.name == "postgresql":
        with db.engine.begin() as conn:
            conn.execute(text("SELECT pg_advisory_xact_lock(727274)"))
            db.metadata.create_all(bind=conn)
    else:
        db.create_all()


def create_app(config=None):
    app = Flask(__name__)
    app.config.update(
        SQLALCHEMY_DATABASE_URI=_db_url(),
        SQLALCHEMY_ENGINE_OPTIONS={"pool_pre_ping": True, "pool_size": 5, "max_overflow": 5, "pool_recycle": 1800},
        MAX_CONTENT_LENGTH=64 * 1024,
        SEND_FILE_MAX_AGE_DEFAULT=timedelta(days=30),  # static files are cache-busted with ?v=
    )
    if config:
        app.config.update(config)
        if "SQLALCHEMY_DATABASE_URI" in config:
            app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {}

    db.init_app(app)
    app.jinja_env.globals["asset_v"] = int(time.time())

    from .api import bp as api_bp
    from .views import bp as views_bp
    app.register_blueprint(api_bp)
    app.register_blueprint(views_bp)

    # ---- optional HTTP Basic auth for UI + API: BASIC_AUTH=user:password ----
    creds = os.getenv("BASIC_AUTH", "")
    if ":" in creds and not app.config.get("TESTING"):
        user, pw = creds.split(":", 1)

        @app.before_request
        def _auth():
            if request.path == "/api/health":
                return None
            a = request.authorization
            if a and hmac.compare_digest((a.username or "").encode(), user.encode()) \
                    and hmac.compare_digest((a.password or "").encode(), pw.encode()):
                return None
            return Response("Authentication required", 401, {"WWW-Authenticate": 'Basic realm="Stockly"'})

    @app.after_request
    def _security_headers(r):
        r.headers.setdefault("X-Content-Type-Options", "nosniff")
        r.headers.setdefault("Referrer-Policy", "same-origin")
        r.headers.setdefault("Content-Security-Policy",
                             "default-src 'self'; img-src 'self' data:; frame-ancestors 'none'")
        return r

    @app.errorhandler(Exception)
    def _errors(e):
        is_api = request.path.startswith("/api")
        if isinstance(e, HTTPException):
            return (jsonify(error=e.description), e.code) if is_api else e
        app.logger.exception("Unhandled error")
        db.session.rollback()
        return (jsonify(error="Internal server error"), 500) if is_api else ("Internal server error", 500)

    with app.app_context():
        _init_db()

    from .seed import register
    register(app)
    return app
