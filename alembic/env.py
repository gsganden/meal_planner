from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# from meal_planner.database import DATA_DIR # Replaced by config import
from meal_planner.config import CONTAINER_DB_FULL_PATH
from meal_planner.models import SQLModel

# This is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = SQLModel.metadata  # Using SQLModel's metadata

# Other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    # Get connection from context attributes if available (passed by tests)
    connection = config.attributes.get("connection", None)

    if connection is None:
        # Fallback to creating engine from config (for CLI / deploy.py runs)
        connectable = engine_from_config(
            config.get_section(config.config_ini_section, {}),
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )
        with connectable.connect() as connection:
            # Conditionally create data directory
            current_url = str(connection.engine.url)
            if not (current_url == "sqlite:///:memory:" or ":memory:" in current_url):
                CONTAINER_DB_FULL_PATH.parent.mkdir(parents=True, exist_ok=True)

            context.configure(connection=connection, target_metadata=target_metadata)

            with context.begin_transaction():
                context.run_migrations()
    else:
        # Use the connection passed via attributes (from tests)
        # The test fixture manages the connection lifecycle and transaction
        context.configure(connection=connection, target_metadata=target_metadata)
        # Assume the test setup handles the transaction begin/commit/rollback
        # We just run the migrations within whatever transaction context is provided.
        with (
            context.begin_transaction()
        ):  # Still needed for Alembic's internal mechanics
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
