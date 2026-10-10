"""Record how a job snapshot was extracted."""

from alembic import op
import sqlalchemy as sa


revision = "0002_job_snapshot_extraction"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {item["name"] for item in sa.inspect(op.get_bind()).get_columns("job_snapshots")}
    if "extraction_method" not in columns:
        op.add_column(
            "job_snapshots",
            sa.Column("extraction_method", sa.String(length=64), nullable=False, server_default="provider_api"),
        )


def downgrade() -> None:
    columns = {item["name"] for item in sa.inspect(op.get_bind()).get_columns("job_snapshots")}
    if "extraction_method" in columns:
        op.drop_column("job_snapshots", "extraction_method")
