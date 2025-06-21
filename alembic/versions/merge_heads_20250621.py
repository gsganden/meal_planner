"""Merge heads

Revision ID: merge_heads_20250621
Revises: 3a4b5c6d7e8f, b7c6e000a7e5
Create Date: 2025-06-21 12:00:00.000000

"""

from typing import Sequence, Union

revision: str = "merge_heads_20250621"
down_revision: Union[str, None] = ("3a4b5c6d7e8f", "b7c6e000a7e5")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
