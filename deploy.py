import os

import modal

from alembic import command
from alembic.config import Config
from meal_planner.config import (
    ALEMBIC_DIR_NAME,
    ALEMBIC_DIR_PATH_IN_CONTAINER,
    ALEMBIC_INI_PATH_IN_CONTAINER,
    CONTAINER_DATA_DIR,
    CONTAINER_DB_FULL_PATH,
    CONTAINER_MAIN_DATABASE_URL,
)
from meal_planner.main import app as fasthtml_app

app = modal.App("meal-planner")

volume = modal.Volume.from_name("meal-planner-data", create_if_missing=True)

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install_from_pyproject("pyproject.toml")
    .add_local_file("alembic.ini", remote_path=str(ALEMBIC_INI_PATH_IN_CONTAINER))
    .add_local_dir(ALEMBIC_DIR_NAME, remote_path=str(ALEMBIC_DIR_PATH_IN_CONTAINER))
    .add_local_python_source("meal_planner")
    .add_local_dir("prompt_templates", remote_path="/root/prompt_templates")
)

google_api_key_secret = modal.Secret.from_dict(
    {"GOOGLE_API_KEY": os.environ["GOOGLE_API_KEY"]}
)


def _check_api_key():
    if "GOOGLE_API_KEY" not in os.environ:
        raise SystemExit("GOOGLE_API_KEY environment variable not set.")


def _run_migrations():
    CONTAINER_DB_FULL_PATH.parent.mkdir(parents=True, exist_ok=True)
    alembic_cfg = Config(str(ALEMBIC_INI_PATH_IN_CONTAINER))
    alembic_cfg.set_main_option("script_location", str(ALEMBIC_DIR_PATH_IN_CONTAINER))
    alembic_cfg.set_main_option("sqlalchemy.url", CONTAINER_MAIN_DATABASE_URL)
    command.upgrade(alembic_cfg, "head")
    print("Database migrations applied.")


@app.function(
    image=image,
    secrets=[google_api_key_secret],
    volumes={str(CONTAINER_DATA_DIR): volume},
)
@modal.asgi_app()
def web():
    _run_migrations()
    _check_api_key()
    return fasthtml_app
