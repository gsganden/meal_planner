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
    volumes={str(CONTAINER_DATA_DIR): volume},
)
def fix_null_recipe_ids():
    """Fix the NULL recipe ID that's causing validation errors."""
    from meal_planner.database import get_session
    from sqlalchemy import text
    from uuid import uuid4
    
    session_gen = get_session()
    session = next(session_gen)
    
    try:
        # Check for NULL recipe IDs
        result = session.execute(text("SELECT COUNT(*) FROM recipes WHERE id IS NULL"))
        null_id_count = result.scalar()
        print(f"Found {null_id_count} recipes with NULL ids")
        
        if null_id_count == 0:
            print("No NULL recipe IDs found - database is already fixed")
            return
            
        # Get records with NULL ids to see what we're dealing with
        result = session.execute(text("SELECT name, created_at FROM recipes WHERE id IS NULL"))
        null_records = result.fetchall()
        print(f"Records with NULL ids:")
        for record in null_records:
            print(f"  - {record[0][:50]}... (created: {record[1]})")
        
        # Option 1: Delete records with NULL ids (if they're duplicates or corrupted)
        # Option 2: Assign new UUIDs to NULL id records
        
        print("\nFixing NULL recipe IDs by assigning new UUIDs...")
        
        # For each NULL id record, assign a new UUID
        count = 0
        while True:
            result = session.execute(text("SELECT rowid FROM recipes WHERE id IS NULL LIMIT 1"))
            row = result.fetchone()
            if not row:
                break
                
            new_uuid = str(uuid4())
            session.execute(
                text("UPDATE recipes SET id = :new_id WHERE rowid = :rowid"),
                {"new_id": new_uuid, "rowid": row[0]}
            )
            count += 1
            print(f"Assigned UUID {new_uuid} to record {count}")
            
        session.commit()
        print(f"Successfully fixed {count} records with NULL IDs")
        
        # Verify the fix
        result = session.execute(text("SELECT COUNT(*) FROM recipes WHERE id IS NULL"))
        remaining_null = result.scalar()
        print(f"Remaining NULL IDs: {remaining_null}")
        
    except Exception as e:
        session.rollback()
        print(f"❌ Error fixing NULL recipe IDs: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        session.close()


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
