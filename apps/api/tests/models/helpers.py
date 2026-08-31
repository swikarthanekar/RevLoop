"""Shared helpers for PostgreSQL metadata validation without a live server."""

from __future__ import annotations

from sqlalchemy import BigInteger, Float, Index, Numeric, UniqueConstraint
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from app.db.base import Base


def pg_dialect() -> postgresql.dialect:
    return postgresql.dialect()


def compile_table(table_name: str) -> str:
    table = Base.metadata.tables[table_name]
    return str(CreateTable(table).compile(dialect=pg_dialect()))


def compile_index(index: Index) -> str:
    return str(CreateIndex(index).compile(dialect=pg_dialect()))


def table_indexes(table_name: str) -> list[Index]:
    return list(Base.metadata.tables[table_name].indexes)


def table_unique_constraints(table_name: str) -> list[UniqueConstraint]:
    return [
        constraint
        for constraint in Base.metadata.tables[table_name].constraints
        if isinstance(constraint, UniqueConstraint)
    ]


def column_type_name(table_name: str, column_name: str) -> str:
    column = Base.metadata.tables[table_name].c[column_name]
    return column.type.__class__.__name__


def is_bigint(table_name: str, column_name: str) -> bool:
    return isinstance(Base.metadata.tables[table_name].c[column_name].type, BigInteger)


def is_numeric_7_6(table_name: str, column_name: str) -> bool:
    col_type = Base.metadata.tables[table_name].c[column_name].type
    return isinstance(col_type, Numeric) and col_type.precision == 7 and col_type.scale == 6


def is_jsonb(table_name: str, column_name: str) -> bool:
    col_type = Base.metadata.tables[table_name].c[column_name].type
    return col_type.__class__.__name__ == "JSONB"


def is_uuid(table_name: str, column_name: str) -> bool:
    col_type = Base.metadata.tables[table_name].c[column_name].type
    return col_type.__class__.__name__ == "UUID"


def has_float_money_columns() -> list[str]:
    offenders: list[str] = []
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if column.name.endswith("_minor") and isinstance(column.type, (Float,)):
                offenders.append(f"{table.name}.{column.name}")
    return offenders
