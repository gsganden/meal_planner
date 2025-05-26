import os

import modal

app = modal.App("meal-planner-web-only")

volume = modal.Volume.from_name("meal-planner-data", create_if_missing=True)

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install_from_pyproject("pyproject.toml")
    .add_local_python_source("meal_planner")
    .add_local_dir("meal_planner/static", remote_path="/root/meal_planner/static")
    .add_local_dir("prompt_templates", remote_path="/root/prompt_templates")
)


def _check_api_key():
    if "GOOGLE_API_KEY" not in os.environ:
        raise SystemExit("GOOGLE_API_KEY environment variable not set.")


google_api_key_secret = None
if "GOOGLE_API_KEY" in os.environ:
    google_api_key_secret = modal.Secret.from_dict(
        {"GOOGLE_API_KEY": os.environ["GOOGLE_API_KEY"]}
    )


@app.function(
    image=image,
    secrets=[google_api_key_secret] if google_api_key_secret else [],
    volumes={"/data": volume},
)
@modal.asgi_app()
def web():
    _check_api_key()
    from meal_planner.main import app as fasthtml_app

    return fasthtml_app
