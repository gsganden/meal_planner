"""Database connection and session management for the Meal Planner application."""

from sqlmodel import Session, create_engine

from meal_planner.config import CONTAINER_MAIN_DATABASE_URL

ENGINE = create_engine(
    CONTAINER_MAIN_DATABASE_URL, connect_args={"check_same_thread": False}
)


def get_session():
    """Provide a database session for dependency injection.

    This generator function creates a SQLModel session that is properly
    managed and closed after use. It's designed to be used with FastAPI's
    dependency injection system or similar contexts.

    Yields:
        Session: A SQLModel database session connected to the configured
        database. The session is automatically closed when the generator
        exits.

    Example:
        @app.get("/recipes")
        def get_recipes(session: Session = Depends(get_session)):
            return session.exec(select(Recipe)).all()
    """
    with Session(ENGINE) as session:
        yield session
