"""add parts code review: pg_trgm, prev_codes, review tasks table

Revision ID: y8z9a0b1c2d3
Revises: x7y8z9a0b1c2
Create Date: 2026-04-27
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'y8z9a0b1c2d3'
down_revision = 'x7y8z9a0b1c2'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Extensión pg_trgm para similarity()
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # 2. prev_codes en parts_references (historial de hasta 2 códigos anteriores)
    op.add_column('parts_references',
        sa.Column('prev_codes', postgresql.JSONB(), server_default='[]', nullable=False))

    # 3. Tabla de tareas de revisión de cambio de código
    op.create_table(
        'parts_code_review_tasks',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('existing_code', sa.String(100), nullable=False),
        sa.Column('candidate_code', sa.String(100), nullable=False),
        sa.Column('existing_description', sa.String(500), nullable=True),
        sa.Column('candidate_description', sa.String(500), nullable=True),
        sa.Column('similarity_score', sa.Numeric(5, 4), nullable=True),
        sa.Column('status', sa.String(20), server_default='pending', nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.Column('resolved_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(['resolved_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_pcrt_status',         'parts_code_review_tasks', ['status'])
    op.create_index('ix_pcrt_existing_code',  'parts_code_review_tasks', ['existing_code'])
    op.create_index('ix_pcrt_candidate_code', 'parts_code_review_tasks', ['candidate_code'])

    # 4. Índices GiST para similarity() rápido
    op.execute("CREATE INDEX IF NOT EXISTS ix_parts_ref_desc_trgm ON parts_references USING gist (description gist_trgm_ops)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_spi_desc_trgm ON spare_part_items USING gist (description gist_trgm_ops)")

    # 5. Umbral de similitud por defecto en system_config
    op.execute("""
        INSERT INTO system_config (key, value)
        VALUES ('parts_similarity_threshold', '0.9')
        ON CONFLICT (key) DO NOTHING
    """)


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_spi_desc_trgm")
    op.execute("DROP INDEX IF EXISTS ix_parts_ref_desc_trgm")
    op.drop_index('ix_pcrt_candidate_code', table_name='parts_code_review_tasks')
    op.drop_index('ix_pcrt_existing_code',  table_name='parts_code_review_tasks')
    op.drop_index('ix_pcrt_status',         table_name='parts_code_review_tasks')
    op.drop_table('parts_code_review_tasks')
    op.drop_column('parts_references', 'prev_codes')
