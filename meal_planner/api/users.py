"""REST API endpoints for user CRUD operations."""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from meal_planner.database import get_session
from meal_planner.models import User

logger = logging.getLogger(__name__)

API_ROUTER = APIRouter()


@API_ROUTER.get("/v0/users/{user_id}", response_model=User)
async def get_user_by_id(
    user_id: UUID, session: Annotated[Session, Depends(get_session)]
):
    """Retrieve a specific user by their ID.

    Fetches a single user from the database using their UUID primary key.
    Returns 404 if the user doesn't exist.

    Args:
        user_id: Unique identifier of the user to retrieve.
        session: Database session from dependency injection.

    Returns:
        The requested user if found.

    Raises:
        HTTPException: 404 if user not found, 500 if database error.
    """
    try:
        user = session.get(User, user_id)
    except Exception as e:
        logger.error(
            "Database error fetching user ID %s: %s", user_id, e, exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error retrieving user",
        ) from e

    if user is None:
        logger.warning("User with ID %s not found.", user_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    return user
