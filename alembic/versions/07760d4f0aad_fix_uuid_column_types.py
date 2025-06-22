"""fix_uuid_column_types

Revision ID: 07760d4f0aad
Revises: merge_heads_20250621
Create Date: 2025-06-22 10:20:12.278769

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "07760d4f0aad"
down_revision: Union[str, None] = "merge_heads_20250621"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema to use proper UUID column types."""
    # Fix recipes table UUID column
    with op.batch_alter_table("recipes") as batch_op:
        batch_op.alter_column("id", type_=sa.UUID(), existing_type=sa.String(36))

    # Fix users table UUID column
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column("id", type_=sa.UUID(), existing_type=sa.String(36))


def downgrade() -> None:
    """Downgrade schema to use String UUID columns."""
    # Revert recipes table UUID column
    with op.batch_alter_table("recipes") as batch_op:
        batch_op.alter_column("id", type_=sa.String(36), existing_type=sa.UUID())

    # Revert users table UUID column
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column("id", type_=sa.String(36), existing_type=sa.UUID())
