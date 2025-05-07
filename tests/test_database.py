import pytest
from sqlmodel import Session

from meal_planner.database import get_session


@pytest.mark.anyio
def test_get_session_yields_session():
    """Verify that get_session yields a SQLModel Session."""
    session_generator = get_session()
    try:
        session = next(session_generator)
        assert isinstance(session, Session)

        with pytest.raises(StopIteration):
            next(session_generator)

    finally:
        session_generator.close()


@pytest.mark.anyio
def test_get_session_functional(dbsession: Session):
    """Verify the session obtained works for a simple query via dbsession fixture."""
    assert isinstance(dbsession, Session)
    from sqlmodel import select

    from meal_planner.models import Recipe

    statement = select(Recipe)
    results = dbsession.exec(statement).all()
    assert isinstance(results, list)
