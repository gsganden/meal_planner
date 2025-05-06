from pathlib import Path
from sqlmodel import Session, create_engine, SQLModel

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_NAME = "meal_planner.db"
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / DB_NAME
DATABASE_URL = f"sqlite:///{DB_PATH.resolve()}"

engine = create_engine(
    DATABASE_URL, echo=True, connect_args={"check_same_thread": False}
)

# Function create_db_and_tables removed as Alembic handles schema creation.


def get_session():
    with Session(engine) as session:
        yield session
