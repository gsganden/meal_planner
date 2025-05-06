# tests/test_database.py
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
        # Coverage is achieved by entering the `with` block and yielding.

        # Ensure the generator can be exhausted (simulates context exit)
        with pytest.raises(StopIteration):
            next(session_generator)

    finally:
        # Explicitly close the generator
        session_generator.close()


@pytest.mark.anyio
def test_get_session_functional(dbsession: Session):
    """Verify the session obtained works for a simple query via dbsession fixture."""
    # This test uses the dbsession fixture, which itself uses get_session
    # via the dependency override mechanism in conftest.py.
    # It confirms the yielded session is functional.
    assert isinstance(dbsession, Session)
    from meal_planner.models import Recipe
    from sqlmodel import select

    statement = select(Recipe)
    results = dbsession.exec(statement).all()
    assert isinstance(results, list)
