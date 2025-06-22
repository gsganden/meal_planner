"""Modal deployment script for the Meal Planner application."""

import logging
import os

import modal

from meal_planner.config import (
    ALEMBIC_DIR_NAME,
    ALEMBIC_DIR_PATH_IN_CONTAINER,
    ALEMBIC_INI_PATH_IN_CONTAINER,
    CONTAINER_DATA_DIR,
    CONTAINER_DB_FULL_PATH,
)

app = modal.App("meal-planner")


def get_volume() -> modal.Volume:
    """Creates or retrieves a Modal Volume for persistent data storage."""
    return modal.Volume.from_name("meal-planner-data", create_if_missing=True)


def create_base_image() -> modal.Image:
    """Creates the base Docker image for Modal functions."""
    return (
        modal.Image.debian_slim(python_version="3.12")
        .pip_install_from_pyproject("pyproject.toml")
        .workdir("/root")
        .add_local_python_source("meal_planner")
        .add_local_dir("meal_planner/static", remote_path="/root/meal_planner/static")
        .add_local_dir("prompt_templates", remote_path="/root/prompt_templates")
    )


def create_google_api_key_secret() -> modal.Secret:
    """Creates a Modal Secret for the Google API Key."""
    deploying = modal.is_local()
    if deploying and "GOOGLE_API_KEY" not in os.environ:
        raise ValueError(
            "GOOGLE_API_KEY environment variable not found in the local environment "
            "where 'modal deploy' is being run. This is required to create the Modal "
            "Secret."
        )
    return modal.Secret.from_local_environ(["GOOGLE_API_KEY"])


base_image = create_base_image()
volume = get_volume()


@app.function(
    image=base_image.add_local_file(
        "alembic.ini", remote_path=str(ALEMBIC_INI_PATH_IN_CONTAINER)
    ).add_local_dir(ALEMBIC_DIR_NAME, remote_path=str(ALEMBIC_DIR_PATH_IN_CONTAINER)),
    volumes={str(CONTAINER_DATA_DIR): volume},
)
def alembic_env():
    """Set up alembic environment for running commands via Modal shell."""
    CONTAINER_DB_FULL_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Environment is now ready for alembic commands via shell
    logging.info("Alembic environment ready for commands.")


@app.function(
    image=base_image,
    secrets=[create_google_api_key_secret()],
    volumes={str(CONTAINER_DATA_DIR): volume},
)
@modal.asgi_app()
def web():
    """Deploy the web application."""
    from meal_planner.main import app as fasthtml_app

    return fasthtml_app
