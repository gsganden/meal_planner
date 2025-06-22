"""debug_uuid_data_format

Revision ID: 86635a760fcf
Revises: 8dda03f6f2c2
Create Date: 2025-06-22 11:10:00.000000

"""

from typing import Sequence, Union
from uuid import UUID

import sqlalchemy as sa

from alembic import op

revision: str = "86635a760fcf"
down_revision: Union[str, None] = "8dda03f6f2c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Debug UUID data format issues."""
    connection = op.get_bind()

    print("\n=== UUID DEBUG INVESTIGATION ===")

    # Check raw SQLite data
    print("1. Raw SQLite data:")
    raw_results = connection.execute(
        sa.text("SELECT id, name FROM recipes LIMIT 3")
    ).fetchall()

    for row in raw_results:
        recipe_id = row[0] if hasattr(row, "__getitem__") else row.id
        recipe_name = row[1] if hasattr(row, "__getitem__") else row.name
        print(
            f"   Raw ID: {recipe_id!r} (type: {type(recipe_id).__name__}) - "
            f"{recipe_name}"
        )

    # Check the problematic ID specifically
    target_id = "92db039f-3d82-465a-a8a7-67f63aa8bf71"
    result = connection.execute(
        sa.text("SELECT COUNT(*) FROM recipes WHERE id = :id"), {"id": target_id}
    ).fetchone()
    print(f"2. Count for {target_id}: {result[0] if result else 'No result'}")

    # Check if it's a string format issue
    result2 = connection.execute(
        sa.text("SELECT id FROM recipes WHERE id LIKE :pattern LIMIT 1"),
        {"pattern": f"%{target_id[:8]}%"},
    ).fetchone()
    if result2:
        found_id = result2[0]
        print(f"3. Found similar ID: {found_id!r}")
        print(f"   Are they equal? {found_id == target_id}")
        print(
            f"   Length comparison: stored={len(str(found_id))}, "
            f"target={len(target_id)}"
        )
    else:
        print("3. No similar ID found")

    # Test UUID conversion
    print("4. Testing UUID conversion:")
    for row in raw_results[:1]:  # Just test first one
        recipe_id = row[0] if hasattr(row, "__getitem__") else row.id
        try:
            uuid_obj = UUID(str(recipe_id))
            print(f"   Successfully converted {recipe_id!r} to UUID: {uuid_obj}")

            # Test if we can find it using the UUID object
            result3 = connection.execute(
                sa.text("SELECT name FROM recipes WHERE id = :id"),
                {"id": str(uuid_obj)},
            ).fetchone()
            if result3:
                print(f"   ✓ Found recipe using UUID string: {result3[0]}")
            else:
                print("   ✗ Could not find recipe using UUID string")

        except Exception as e:
            print(f"   ✗ Failed to convert {recipe_id!r} to UUID: {e}")

    print("=== END DEBUG ===\n")


def downgrade() -> None:
    """No downgrade needed for debug migration."""
    pass
