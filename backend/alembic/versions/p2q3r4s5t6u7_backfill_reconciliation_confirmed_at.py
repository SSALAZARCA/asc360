"""backfill confirmed_by/confirmed_at on reconciliation_results confirmed before this field existed

Revision ID: p2q3r4s5t6u7
Revises: ll8m9n0o1p2q
Create Date: 2026-07-10

`confirm_reconciliation` never stamped `reconciliation_results.confirmed_at`
until now, so lots confirmed under the old code have no record of it. Their
"Confirmar recepcion" button would still show as active (nothing to derive
"already confirmed" from) and, worse, a second click would bypass the new
ALREADY_CONFIRMED guard entirely (it also checks confirmed_at) and silently
re-apply the whole reconciliation.

A lot's results are treated as historically confirmed if either signal is
present anywhere in that lot -- both are ONLY ever set by
`confirm_reconciliation`, never by any other code path:
  - a linked `spare_part_items.status` of 'DECLARED' or 'BACKORDER'
  - a `reconciliation_results.result` of 'EXTRA_APPLIED'

`confirmed_at` is backfilled from each row's own `created_at` (best-effort
historical timestamp; the exact confirm time isn't recoverable).
`confirmed_by` is left NULL (unknown actor) -- this is also how the
downgrade tells backfilled rows apart from real confirms, which always set
a real `confirmed_by`.

Known gap (documented, not fixable from data alone): a lot where EVERY
result was PARTIAL and no EXTRA ever got applied to a backorder leaves no
distinguishing signal in this data, and won't be caught by this backfill.
"""
from alembic import op

revision = 'p2q3r4s5t6u7'
down_revision = 'll8m9n0o1p2q'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        WITH confirmed_lots AS (
            SELECT DISTINCT rr.lot_id
            FROM reconciliation_results rr
            JOIN spare_part_items spi ON spi.id = rr.spare_part_item_id
            WHERE spi.status IN ('DECLARED', 'BACKORDER')
            UNION
            SELECT DISTINCT rr.lot_id
            FROM reconciliation_results rr
            WHERE rr.result = 'EXTRA_APPLIED'
        )
        UPDATE reconciliation_results rr
        SET confirmed_at = rr.created_at
        FROM confirmed_lots cl
        WHERE rr.lot_id = cl.lot_id
          AND rr.confirmed_at IS NULL
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE reconciliation_results
        SET confirmed_at = NULL
        WHERE confirmed_by IS NULL
    """)
