"""fix_null_timestamps

Fix any existing NULL timestamp values in recipes and users tables.
This addresses the issue where old records have NULL timestamps but
the new model definitions expect non-NULL datetime values.

Revision ID: 9548ad40c2e4
Revises: 86635a760fcf
Create Date: 2025-06-22 12:00:22.995671

"""
from typing import Sequence, Union
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision: str = '9548ad40c2e4'
down_revision: Union[str, None] = '86635a760fcf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Fix NULL timestamp values in existing records."""
    connection = op.get_bind()
    
    # Use a fixed timestamp for consistency
    fixed_timestamp = datetime.now(timezone.utc).isoformat()
    
    print(f"Fixing NULL timestamps with: {fixed_timestamp}")
    
    # Fix NULL created_at in recipes
    result = connection.execute(
        sa.text("UPDATE recipes SET created_at = :timestamp WHERE created_at IS NULL"),
        {"timestamp": fixed_timestamp}
    )
    print(f"Fixed {result.rowcount} recipes with NULL created_at")
    
    # Fix NULL updated_at in recipes  
    result = connection.execute(
        sa.text("UPDATE recipes SET updated_at = :timestamp WHERE updated_at IS NULL"),
        {"timestamp": fixed_timestamp}
    )
    print(f"Fixed {result.rowcount} recipes with NULL updated_at")
    
    # Fix NULL created_at in users
    result = connection.execute(
        sa.text("UPDATE users SET created_at = :timestamp WHERE created_at IS NULL"),
        {"timestamp": fixed_timestamp}
    )
    print(f"Fixed {result.rowcount} users with NULL created_at")
    
    # Fix NULL updated_at in users
    result = connection.execute(
        sa.text("UPDATE users SET updated_at = :timestamp WHERE updated_at IS NULL"), 
        {"timestamp": fixed_timestamp}
    )
    print(f"Fixed {result.rowcount} users with NULL updated_at")


def downgrade() -> None:
    """Cannot downgrade - would set valid timestamps back to NULL."""
    raise NotImplementedError(
        "Cannot downgrade timestamp fixes - would lose data integrity"
    )
