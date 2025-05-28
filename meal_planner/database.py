"""Database connection and session management for the Meal Planner application."""

from sqlmodel import Session, create_engine

from meal_planner.config import CONTAINER_MAIN_DATABASE_URL

engine = create_engine(
    CONTAINER_MAIN_DATABASE_URL, echo=True, connect_args={"check_same_thread": False}
)


def get_session():
    with Session(engine) as session:
        yield session
