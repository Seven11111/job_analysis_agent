"""Create the initial job research schema."""

from alembic import op

from src.db import models  # noqa: F401
from src.db.base import Base


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The first migration derives the initial schema from the reviewed ORM
    # model set. Future migrations should use explicit Alembic operations.
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
