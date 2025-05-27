import logging
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

app = modal.App("meal-planner")


def create_volume() -> modal.Volume:
    return modal.Volume.from_name("meal-planner-data", create_if_missing=True)


def create_base_image() -> modal.Image:
    return (
        modal.Image.debian_slim(python_version="3.12")
        .pip_install_from_pyproject("pyproject.toml")
        .add_local_python_source("meal_planner")
        .add_local_dir("meal_planner/static", remote_path="/root/meal_planner/static")
        .add_local_dir("prompt_templates", remote_path="/root/prompt_templates")
    )


def create_google_api_key_secret() -> modal.Secret | None:
    if "GOOGLE_API_KEY" in os.environ:
        return modal.Secret.from_dict({"GOOGLE_API_KEY": os.environ["GOOGLE_API_KEY"]})
    return None


base_image = create_base_image()
volume = create_volume()


@app.function(
    image=base_image.add_local_file(
        "alembic.ini", remote_path=str(ALEMBIC_INI_PATH_IN_CONTAINER)
    ).add_local_dir(ALEMBIC_DIR_NAME, remote_path=str(ALEMBIC_DIR_PATH_IN_CONTAINER)),
    volumes={str(CONTAINER_DATA_DIR): volume},
)
def migrate_db():
    """Run database migrations."""
    CONTAINER_DB_FULL_PATH.parent.mkdir(parents=True, exist_ok=True)
    alembic_cfg = Config(str(ALEMBIC_INI_PATH_IN_CONTAINER))
    alembic_cfg.set_main_option("script_location", str(ALEMBIC_DIR_PATH_IN_CONTAINER))
    alembic_cfg.set_main_option("sqlalchemy.url", CONTAINER_MAIN_DATABASE_URL)
    command.upgrade(alembic_cfg, "head")
    logging.info("Database migrations applied.")


@app.function(
    image=base_image,
    secrets=[create_google_api_key_secret()],
    volumes={str(CONTAINER_DATA_DIR): volume},
)
@modal.asgi_app()
def web():
    """Deploy the web application."""
    from meal_planner.main import app as fasthtml_app

    if os.environ.get("GOOGLE_API_KEY") is None:
        raise ValueError("GOOGLE_API_KEY is not set")

    return fasthtml_app
