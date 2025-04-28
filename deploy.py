import os
from pathlib import Path

import modal

from meal_planner.main import app as fasthtml_app

app = modal.App("meal-planner")

volume = modal.Volume.from_name("meal-planner-data", create_if_missing=True)

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install_from_pyproject("pyproject.toml")
    .add_local_python_source("meal_planner")
    .add_local_dir("prompt_templates", remote_path="/root/prompt_templates")
)

google_api_key_secret = modal.Secret.from_dict(
    {"GOOGLE_API_KEY": os.environ["GOOGLE_API_KEY"]}
)


def _check_api_key():
    if "GOOGLE_API_KEY" not in os.environ:
        raise SystemExit("GOOGLE_API_KEY environment variable not set.")


@app.function(image=image, secrets=[google_api_key_secret], volumes={"/data": volume})
@modal.asgi_app()
def web():
    _check_api_key()
    (Path("/data")).mkdir(parents=True, exist_ok=True)
    return fasthtml_app
