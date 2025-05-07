from logging.config import fileConfig

from alembic import context
from meal_planner.database import DATA_DIR
from meal_planner.database import engine as app_engine
from meal_planner.models import SQLModel

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def run_migrations() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    connectable = app_engine

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=SQLModel.metadata)

        with context.begin_transaction():
            context.run_migrations()


run_migrations()
