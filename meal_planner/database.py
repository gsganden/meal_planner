from pathlib import Path

from sqlmodel import Session, create_engine

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_NAME = "meal_planner.db"

DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / DB_NAME
DATABASE_URL = f"sqlite:///{DB_PATH.resolve()}"

engine = create_engine(
    DATABASE_URL, echo=True, connect_args={"check_same_thread": False}
)


def create_db_and_tables():
    """Initialize the database and create tables based on SQLModel metadata.
    This function is typically used for initial setup or in development/testing.
    For production, Alembic migrations should manage the schema.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    pass  # Alembic will handle table creation


# Future: Alembic will use this engine. We might also need session management here.
def get_session():
    with Session(engine) as session:
        yield session
