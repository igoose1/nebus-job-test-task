"""Use now() for timestamptz server defaults.

Revision ID: eff1a3f866d5
Revises: d25426c4b629
Create Date: 2026-09-20 15:36:18.053639

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "eff1a3f866d5"
down_revision: str | Sequence[str] | None = "d25426c4b629"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLUMNS = [
    ("payments", "created_at"),
    ("outbox_messages", "created_at"),
    ("outbox_messages", "next_attempt_at"),
]


def upgrade() -> None:
    for table, column in COLUMNS:
        op.alter_column(table, column, server_default=sa.func.now())


def downgrade() -> None:
    for table, column in COLUMNS:
        op.alter_column(table, column, server_default=sa.text("timezone('utc', now())"))
