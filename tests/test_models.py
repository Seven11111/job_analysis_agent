from src.db import models  # noqa: F401
from src.db.base import Base


def test_initial_tables_are_registered() -> None:
    expected = {
        "job_sources",
        "jobs",
        "job_snapshots",
        "job_skills",
        "candidate_profiles",
        "resume_versions",
        "profile_facts",
        "applications",
        "application_status_definitions",
        "application_status_events",
        "job_matches",
        "agent_sessions",
        "agent_messages",
        "agent_run_events",
        "app_settings",
    }

    assert expected.issubset(Base.metadata.tables)
