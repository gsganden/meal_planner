"""Database connection and session management for the Meal Planner application.

This module provides SQLModel/SQLAlchemy database engine configuration and
session management utilities. It handles the creation of database connections
and provides functions for initializing the database schema.
"""

from sqlmodel import Session, SQLModel, create_engine, select

from meal_planner.config import CONTAINER_MAIN_DATABASE_URL

# Don't check validity for SQLite
engine = create_engine(CONTAINER_MAIN_DATABASE_URL, connect_args={"check_same_thread": False})


def create_db_and_tables() -> None:
    """Initialize the database schema by creating all defined tables.
    
    This function uses SQLModel's metadata to create all tables that are
    defined in the application's models. It should be called during
    application startup or database initialization. If tables already
    exist, they will not be recreated.
    
    Note:
        This is primarily used for development and testing. Production
        deployments should use Alembic migrations for schema management.
    """
    SQLModel.metadata.create_all(engine)


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
    with Session(engine) as session:
        yield session
