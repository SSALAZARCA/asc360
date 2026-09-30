"""Helper to inspect the ON CONFLICT DO UPDATE SET clause of an upsert.

Asserts on the compiled Postgres SQL rather than SQLAlchemy's private
statement attributes, which changed shape in SQLAlchemy 2.1.
"""
import re
from typing import Dict

from sqlalchemy.dialects import postgresql


def upsert_set_clause(stmt) -> Dict[str, str]:
    """Return `{column: rendered expression}` of the DO UPDATE SET clause."""
    sql = str(stmt.compile(dialect=postgresql.dialect()))
    clause = sql.split("DO UPDATE SET", 1)[1]
    pairs = re.split(r",\s+(?=\w+ = )", clause.strip())
    return {p.split(" = ", 1)[0]: p.split(" = ", 1)[1] for p in pairs}
