"""Ensure Agent conversation tables exist for databases created before Phase 6."""

from alembic import op
import sqlalchemy as sa


revision = "0004_agent_sessions"
down_revision = "0003_resume_attachments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "agent_sessions" not in tables:
        op.create_table(
            "agent_sessions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("profile_id", sa.Integer(), sa.ForeignKey("candidate_profiles.id"), nullable=False),
            sa.Column("title", sa.String(length=200)),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_agent_sessions_profile_id", "agent_sessions", ["profile_id"])

    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "agent_messages" not in tables:
        op.create_table(
            "agent_messages",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("session_id", sa.Integer(), sa.ForeignKey("agent_sessions.id"), nullable=False),
            sa.Column("role", sa.String(length=16), nullable=False),
            sa.Column("content_text", sa.Text()),
            sa.Column("structured_content", sa.Text()),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_agent_messages_session_id", "agent_messages", ["session_id"])

    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "agent_run_events" not in tables:
        op.create_table(
            "agent_run_events",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("session_id", sa.Integer(), sa.ForeignKey("agent_sessions.id"), nullable=False),
            sa.Column("message_id", sa.Integer(), sa.ForeignKey("agent_messages.id")),
            sa.Column("run_id", sa.String(length=64), nullable=False),
            sa.Column("sequence", sa.Integer(), nullable=False),
            sa.Column("event_type", sa.String(length=32), nullable=False),
            sa.Column("name", sa.String(length=128)),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("payload", sa.Text()),
            sa.Column("started_at", sa.DateTime()),
            sa.Column("completed_at", sa.DateTime()),
            sa.Column("error_message", sa.Text()),
            sa.UniqueConstraint("run_id", "sequence", name="uq_agent_run_events_sequence"),
        )
        op.create_index("ix_agent_run_events_session_id", "agent_run_events", ["session_id"])
        op.create_index("ix_agent_run_events_run_id", "agent_run_events", ["run_id"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "agent_run_events" in tables:
        indexes = {item["name"] for item in inspector.get_indexes("agent_run_events")}
        for name in ("ix_agent_run_events_run_id", "ix_agent_run_events_session_id"):
            if name in indexes:
                op.drop_index(name, table_name="agent_run_events")
        op.drop_table("agent_run_events")
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "agent_messages" in tables:
        indexes = {item["name"] for item in sa.inspect(op.get_bind()).get_indexes("agent_messages")}
        if "ix_agent_messages_session_id" in indexes:
            op.drop_index("ix_agent_messages_session_id", table_name="agent_messages")
        op.drop_table("agent_messages")
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "agent_sessions" in tables:
        indexes = {item["name"] for item in sa.inspect(op.get_bind()).get_indexes("agent_sessions")}
        if "ix_agent_sessions_profile_id" in indexes:
            op.drop_index("ix_agent_sessions_profile_id", table_name="agent_sessions")
        op.drop_table("agent_sessions")
