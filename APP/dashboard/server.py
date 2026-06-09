import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, send_from_directory
from flask_cors import CORS
from apscheduler.schedulers.background import BackgroundScheduler

# 确保项目根目录在 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import sqlite3

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(APP_DIR, "dashboard.db")
LOG_PATH = os.path.join(APP_DIR, "dashboard.log")
MIGRATIONS_DIR = os.path.join(APP_DIR, "migrations")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """执行未完成的 migrations"""
    conn = get_db()
    cursor = conn.cursor()
    
    # 确保 migrations 表存在
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    """)
    
    # 获取已执行的迁移
    cursor.execute("SELECT name FROM schema_migrations")
    executed = {row["name"] for row in cursor.fetchall()}
    
    # 执行未执行的迁移
    for fname in sorted(os.listdir(MIGRATIONS_DIR)):
        if fname.endswith(".sql") and fname not in executed:
            with open(os.path.join(MIGRATIONS_DIR, fname), "r") as f:
                sql = f.read()
            cursor.executescript(sql)
            cursor.execute("INSERT INTO schema_migrations (name) VALUES (?)", (fname,))
            print(f"[dashboard] Executed migration: {fname}")
    
    conn.commit()
    conn.close()


def setup_logging():
    handler = RotatingFileHandler(LOG_PATH, maxBytes=5*1024*1024, backupCount=3)
    handler.setFormatter(logging.Formatter(
        "[%(asctime)s] %(levelname)s [%(name)s] %(message)s"
    ))
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)


# Flask app
app = Flask(__name__, static_folder="static", static_url_path="/static")
app.config["SECRET_KEY"] = "dashboard-secret-key"
CORS(app)

setup_logging()

# APScheduler
scheduler = BackgroundScheduler(timezone="Asia/Shanghai")

# Import and register blueprints after app is created
from APP.dashboard.apis import register_blueprints
register_blueprints(app, scheduler)

# Store scheduler in app.extensions so blueprints can access it
if not hasattr(app, "extensions"):
    app.extensions = {}
app.extensions["scheduler"] = scheduler

# Init database
init_db()

# Start scheduler
scheduler.start()
app.logger.info("Dashboard server started, scheduler running")


DIST_DIR = os.path.join(APP_DIR, "static", "dist")


def _dist_ready() -> bool:
    return os.path.isfile(os.path.join(DIST_DIR, "index.html"))


@app.route("/")
def index():
    """服务 Vite 构建产物 index.html。"""
    if not _dist_ready():
        return ("Frontend build missing. Run `cd APP/dashboard/web && npm run build`.", 503)
    return send_from_directory(DIST_DIR, "index.html")


@app.route("/assets/<path:filename>")
def vite_assets(filename: str):
    """Vite 构建后的静态资源（JS/CSS/字体等）。"""
    assets_dir = os.path.join(DIST_DIR, "assets")
    return send_from_directory(assets_dir, filename)


@app.route("/<path:filename>")
def dist_root_files(filename: str):
    """兜底：根级静态文件优先 dist，无文件时回落到 index.html（交给 vue-router）。"""
    if filename.startswith("api/"):
        return ("Not Found", 404)
    dist_path = os.path.join(DIST_DIR, filename)
    if os.path.isfile(dist_path):
        return send_from_directory(DIST_DIR, filename)
    if _dist_ready():
        return send_from_directory(DIST_DIR, "index.html")
    return ("Not Found", 404)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
