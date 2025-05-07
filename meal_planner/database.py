from pathlib import Path

from sqlmodel import Session, create_engine

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DB_NAME = "meal_planner.db"
DB_PATH = DATA_DIR / DB_NAME
DATABASE_URL = f"sqlite:///{DB_PATH.resolve()}"

engine = create_engine(
    DATABASE_URL, echo=True, connect_args={"check_same_thread": False}
)


def get_session():
    with Session(engine) as session:
        yield session
