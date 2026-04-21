"""add quick service type

Revision ID: p6k7l8m9n0o1
Revises: o5j6k7l8m9n0
Branch Labels: None
Depends On: None
"""
from alembic import op

revision = 'p6k7l8m9n0o1'
down_revision = 'o5j6k7l8m9n0'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TYPE servicetype ADD VALUE IF NOT EXISTS 'quick'")


def downgrade():
    # PostgreSQL no permite eliminar valores de un enum directamente.
    # Para hacer downgrade habría que recrear el tipo sin 'quick'.
    pass
