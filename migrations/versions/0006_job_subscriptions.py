"""Add local job-search subscriptions and short-lived result previews."""

from alembic import op
import sqlalchemy as sa


revision = "0006_job_subscriptions"
down_revision = "0005_workbench"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())

    if "job_subscriptions" not in tables:
        op.create_table(
            "job_subscriptions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("profile_id", sa.Integer(), sa.ForeignKey("candidate_profiles.id"), nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("filters_json", sa.Text(), nullable=False),
            sa.Column("frequency", sa.String(length=16), nullable=False, server_default="manual"),
            sa.Column("schedule_time", sa.String(length=5), nullable=False, server_default="09:00"),
            sa.Column("weekday", sa.Integer()),
            sa.Column("timezone", sa.String(length=64), nullable=False, server_default="Asia/Shanghai"),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("next_run_at", sa.DateTime()),
            sa.Column("last_run_at", sa.DateTime()),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_job_subscriptions_profile_id", "job_subscriptions", ["profile_id"])
        op.create_index("ix_job_subscriptions_next_run_at", "job_subscriptions", ["next_run_at"])
        op.create_index(
            "ix_job_subscriptions_enabled_next_run", "job_subscriptions", ["enabled", "next_run_at"]
        )

    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "job_subscription_runs" not in tables:
        op.create_table(
            "job_subscription_runs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "subscription_id",
                sa.Integer(),
                sa.ForeignKey("job_subscriptions.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("trigger", sa.String(length=16), nullable=False),
            sa.Column("status", sa.String(length=24), nullable=False, server_default="running"),
            sa.Column("total_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("new_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("provider_results_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("error_message", sa.Text()),
            sa.Column("started_at", sa.DateTime(), nullable=False),
            sa.Column("completed_at", sa.DateTime()),
        )
        op.create_index("ix_job_subscription_runs_subscription_id", "job_subscription_runs", ["subscription_id"])
        op.create_index("ix_job_subscription_runs_started_at", "job_subscription_runs", ["started_at"])
        op.create_index(
            "ix_job_subscription_runs_subscription_started",
            "job_subscription_runs",
            ["subscription_id", "started_at"],
        )

    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "job_subscription_seen_jobs" not in tables:
        op.create_table(
            "job_subscription_seen_jobs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "subscription_id",
                sa.Integer(),
                sa.ForeignKey("job_subscriptions.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("provider", sa.String(length=64), nullable=False),
            sa.Column("identity_hash", sa.String(length=64), nullable=False),
            sa.Column("first_seen_at", sa.DateTime(), nullable=False),
            sa.Column("last_seen_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint(
                "subscription_id", "provider", "identity_hash", name="uq_subscription_seen_identity"
            ),
        )
        op.create_index(
            "ix_job_subscription_seen_jobs_subscription_id", "job_subscription_seen_jobs", ["subscription_id"]
        )

    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "job_subscription_run_items" not in tables:
        op.create_table(
            "job_subscription_run_items",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "run_id",
                sa.Integer(),
                sa.ForeignKey("job_subscription_runs.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("provider", sa.String(length=64), nullable=False),
            sa.Column("identity_hash", sa.String(length=64), nullable=False),
            sa.Column("is_new", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("job_json", sa.Text(), nullable=False),
            sa.Column("saved_job_id", sa.Integer(), sa.ForeignKey("jobs.id")),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("run_id", "provider", "identity_hash", name="uq_subscription_run_item_identity"),
        )
        op.create_index("ix_job_subscription_run_items_run_id", "job_subscription_run_items", ["run_id"])
        op.create_index(
            "ix_job_subscription_run_items_saved_job_id", "job_subscription_run_items", ["saved_job_id"]
        )
        op.create_index(
            "ix_subscription_run_items_run_new", "job_subscription_run_items", ["run_id", "is_new"]
        )


def downgrade() -> None:
    for table, indexes in (
        (
            "job_subscription_run_items",
            ("ix_subscription_run_items_run_new", "ix_job_subscription_run_items_saved_job_id", "ix_job_subscription_run_items_run_id"),
        ),
        ("job_subscription_seen_jobs", ("ix_job_subscription_seen_jobs_subscription_id",)),
        (
            "job_subscription_runs",
            ("ix_job_subscription_runs_subscription_started", "ix_job_subscription_runs_started_at", "ix_job_subscription_runs_subscription_id"),
        ),
        (
            "job_subscriptions",
            ("ix_job_subscriptions_enabled_next_run", "ix_job_subscriptions_next_run_at", "ix_job_subscriptions_profile_id"),
        ),
    ):
        if table not in sa.inspect(op.get_bind()).get_table_names():
            continue
        existing = {item["name"] for item in sa.inspect(op.get_bind()).get_indexes(table)}
        for index in indexes:
            if index in existing:
                op.drop_index(index, table_name=table)
        op.drop_table(table)
