"""Store uploaded resume attachments separately from confirmed resume versions."""

from alembic import op
import sqlalchemy as sa


revision = "0003_resume_attachments"
down_revision = "0002_job_snapshot_extraction"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "resume_attachments" not in tables:
        op.create_table(
            "resume_attachments",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("profile_id", sa.Integer(), sa.ForeignKey("candidate_profiles.id"), nullable=False),
            sa.Column("original_filename", sa.String(length=255), nullable=False),
            sa.Column("storage_filename", sa.String(length=64), nullable=False, unique=True),
            sa.Column("content_type", sa.String(length=128), nullable=False),
            sa.Column("size_bytes", sa.Integer(), nullable=False),
            sa.Column("sha256", sa.String(length=64), nullable=False),
            sa.Column("extracted_text", sa.Text(), nullable=False),
            sa.Column("draft_content", sa.Text(), nullable=False),
            sa.Column("parse_status", sa.String(length=32), nullable=False, server_default="pending_review"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
    indexes = {item["name"] for item in sa.inspect(op.get_bind()).get_indexes("resume_attachments")}
    if "ix_resume_attachments_profile_id" not in indexes:
        op.create_index("ix_resume_attachments_profile_id", "resume_attachments", ["profile_id"])

    columns = {item["name"] for item in sa.inspect(op.get_bind()).get_columns("resume_versions")}
    if "source_attachment_id" not in columns:
        with op.batch_alter_table("resume_versions") as batch_op:
            batch_op.add_column(sa.Column("source_attachment_id", sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                "fk_resume_versions_source_attachment_id",
                "resume_attachments",
                ["source_attachment_id"],
                ["id"],
                ondelete="SET NULL",
            )
    indexes = {item["name"] for item in sa.inspect(op.get_bind()).get_indexes("resume_versions")}
    if "ix_resume_versions_source_attachment_id" not in indexes:
        op.create_index("ix_resume_versions_source_attachment_id", "resume_versions", ["source_attachment_id"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "resume_versions" in inspector.get_table_names():
        columns = {item["name"] for item in inspector.get_columns("resume_versions")}
        if "source_attachment_id" in columns:
            indexes = {item["name"] for item in inspector.get_indexes("resume_versions")}
            if "ix_resume_versions_source_attachment_id" in indexes:
                op.drop_index("ix_resume_versions_source_attachment_id", table_name="resume_versions")
            foreign_keys = {item["name"] for item in sa.inspect(op.get_bind()).get_foreign_keys("resume_versions")}
            with op.batch_alter_table("resume_versions") as batch_op:
                if "fk_resume_versions_source_attachment_id" in foreign_keys:
                    batch_op.drop_constraint("fk_resume_versions_source_attachment_id", type_="foreignkey")
                batch_op.drop_column("source_attachment_id")
    inspector = sa.inspect(op.get_bind())
    if "resume_attachments" in inspector.get_table_names():
        indexes = {item["name"] for item in inspector.get_indexes("resume_attachments")}
        if "ix_resume_attachments_profile_id" in indexes:
            op.drop_index("ix_resume_attachments_profile_id", table_name="resume_attachments")
        op.drop_table("resume_attachments")
