"""create_users_table

Revision ID: 2a3b4c5d6e7f
Revises: 1c66282b9e50
Create Date: 2025-06-09 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "2a3b4c5d6e7f"
down_revision: Union[str, None] = "1c66282b9e50"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "users",
        sa.Column(
            "id",
            sa.String(32),
            sa.CheckConstraint(
                "LENGTH(id) = 32 AND id GLOB "
                "'[0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]"
                "[0-9a-f][0-9a-f][0-9a-f][0-9a-f]"
                "[0-9a-f][0-9a-f][0-9a-f][0-9a-f]"
                "[0-9a-f][0-9a-f][0-9a-f][0-9a-f]"
                "[0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]"
                "[0-9a-f][0-9a-f][0-9a-f][0-9a-f]'",
                name="ck_users_id_uuid_format",
            ),
            primary_key=True,
        ),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )

    op.create_index("ix_users_username", "users", ["username"], unique=True)

    op.execute(
        """
        INSERT INTO users (id, username, created_at, updated_at)
        VALUES (
            '7dfc4e175b0c4e088de18db9e7321711',
            'demo_user',
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP
        )
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")
