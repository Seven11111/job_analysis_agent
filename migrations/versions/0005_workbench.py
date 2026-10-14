"""Add personal workbench todos and interview events."""

from alembic import op
import sqlalchemy as sa


revision = "0005_workbench"
down_revision = "0004_agent_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())

    if "job_todos" not in tables:
        op.create_table(
            "job_todos",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("profile_id", sa.Integer(), sa.ForeignKey("candidate_profiles.id"), nullable=False),
            sa.Column("application_id", sa.Integer(), sa.ForeignKey("applications.id", ondelete="SET NULL")),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("due_at", sa.DateTime()),
            sa.Column("priority", sa.String(length=16), nullable=False, server_default="normal"),
            sa.Column("completed", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("completed_at", sa.DateTime()),
            sa.Column("note", sa.Text()),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_job_todos_profile_id", "job_todos", ["profile_id"])
        op.create_index("ix_job_todos_application_id", "job_todos", ["application_id"])
        op.create_index("ix_job_todos_due_at", "job_todos", ["due_at"])

    if "interview_events" not in set(sa.inspect(op.get_bind()).get_table_names()):
        op.create_table(
            "interview_events",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("profile_id", sa.Integer(), sa.ForeignKey("candidate_profiles.id"), nullable=False),
            sa.Column("application_id", sa.Integer(), sa.ForeignKey("applications.id", ondelete="SET NULL")),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("company_name", sa.String(length=200)),
            sa.Column("position_title", sa.String(length=300)),
            sa.Column("starts_at", sa.DateTime(), nullable=False),
            sa.Column("ends_at", sa.DateTime()),
            sa.Column("timezone", sa.String(length=64), nullable=False, server_default="Asia/Shanghai"),
            sa.Column("interview_format", sa.String(length=24), nullable=False, server_default="unknown"),
            sa.Column("location", sa.String(length=500)),
            sa.Column("meeting_url", sa.String(length=1000)),
            sa.Column("note", sa.Text()),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_interview_events_profile_id", "interview_events", ["profile_id"])
        op.create_index("ix_interview_events_application_id", "interview_events", ["application_id"])
        op.create_index("ix_interview_events_starts_at", "interview_events", ["starts_at"])
        op.create_index(
            "ix_interview_events_profile_starts_at", "interview_events", ["profile_id", "starts_at"]
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "interview_events" in tables:
        indexes = {item["name"] for item in inspector.get_indexes("interview_events")}
        for name in (
            "ix_interview_events_profile_starts_at",
            "ix_interview_events_starts_at",
            "ix_interview_events_application_id",
            "ix_interview_events_profile_id",
        ):
            if name in indexes:
                op.drop_index(name, table_name="interview_events")
        op.drop_table("interview_events")

    if "job_todos" in tables:
        indexes = {item["name"] for item in sa.inspect(op.get_bind()).get_indexes("job_todos")}
        for name in ("ix_job_todos_due_at", "ix_job_todos_application_id", "ix_job_todos_profile_id"):
            if name in indexes:
                op.drop_index(name, table_name="job_todos")
        op.drop_table("job_todos")
