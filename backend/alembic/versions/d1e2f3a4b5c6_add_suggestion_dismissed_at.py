"""add suggestion_dismissed_at to parts_references

Revision ID: d1e2f3a4b5c6
Revises: c9d0e1f2a3b4
Create Date: 2026-08-12

`sdd/parts-description-source-of-truth` PR5 (design D18) -- THE ONE
migration in this entire change. Backs the permanent "never show this
unconfirmed-name suggestion again" dismissal (`POST
/parts/admin/catalog-dismiss-suggestion/{fpn}`). Nullable, no
`server_default`, no backfill -> zero rows change on deploy. Copied
verbatim in shape from the closest precedent, `bb3c4d5e6f7a` (also a
single nullable column added to `parts_references`).
"""
from alembic import op
import sqlalchemy as sa

revision = 'd1e2f3a4b5c6'
down_revision = 'c9d0e1f2a3b4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'parts_references',
        sa.Column('suggestion_dismissed_at', sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('parts_references', 'suggestion_dismissed_at')
