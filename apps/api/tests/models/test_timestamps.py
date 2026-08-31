from sqlalchemy.types import DateTime

import app.models  # noqa: F401
from app.db.base import Base


def test_important_timestamps_are_timezone_aware() -> None:
    timestamp_columns = [
        ("organizations", "created_at"),
        ("organizations", "updated_at"),
        ("recovery_cases", "opened_at"),
        ("recovery_cases", "last_transition_at"),
        ("webhook_events", "received_at"),
        ("audit_logs", "created_at"),
    ]
    for table_name, column_name in timestamp_columns:
        column = Base.metadata.tables[table_name].c[column_name]
        assert isinstance(column.type, DateTime)
        assert column.type.timezone is True


def test_recovery_case_version_defaults_to_one() -> None:
    column = Base.metadata.tables["recovery_cases"].c.version
    assert column.server_default is not None
