"""Add flexible job subscription schedule options."""

from alembic import op
import sqlalchemy as sa


revision = "0007_subscription_frequency_options"
down_revision = "0006_job_subscriptions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("job_subscriptions")}
    if "interval_days" not in columns:
        op.add_column("job_subscriptions", sa.Column("interval_days", sa.Integer(), nullable=True))
    if "month_day" not in columns:
        op.add_column("job_subscriptions", sa.Column("month_day", sa.Integer(), nullable=True))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("job_subscriptions")}
    if "month_day" in columns:
        op.drop_column("job_subscriptions", "month_day")
    if "interval_days" in columns:
        op.drop_column("job_subscriptions", "interval_days")
