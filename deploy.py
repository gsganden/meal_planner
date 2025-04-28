import os
import sqlite3

import modal

from meal_planner.api.recipes import DB_PATH
from meal_planner.main import app as fasthtml_app

app = modal.App("meal-planner")

volume = modal.Volume.from_name("meal-planner-data", create_if_missing=True)

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install_from_pyproject("pyproject.toml")
    .env({"MEAL_PLANNER_DB_PATH": str(DB_PATH)})
    .add_local_python_source("meal_planner")
    .add_local_dir("prompt_templates", remote_path="/root/prompt_templates")
)

google_api_key_secret = modal.Secret.from_dict(
    {"GOOGLE_API_KEY": os.environ["GOOGLE_API_KEY"]}
)


def _check_api_key():
    if "GOOGLE_API_KEY" not in os.environ:
        raise SystemExit("GOOGLE_API_KEY environment variable not set.")


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS recipes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            ingredients TEXT,
            instructions TEXT
        )
        """
    )
    conn.commit()
    conn.close()
    print(f"Database initialized/verified at {DB_PATH}")


@app.function(image=image, secrets=[google_api_key_secret], volumes={"/data": volume})
@modal.asgi_app()
def web():
    _check_api_key()
    init_db()
    return fasthtml_app
