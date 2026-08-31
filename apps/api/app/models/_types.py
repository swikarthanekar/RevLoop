"""Shared SQLAlchemy constraint helpers for ORM models."""

from enum import Enum

from sqlalchemy import CheckConstraint


def enum_check(column: str, enum_cls: type[Enum], name: str) -> CheckConstraint:
    values = ", ".join(f"'{member.value}'" for member in enum_cls)
    return CheckConstraint(f"{column} IN ({values})", name=name)
