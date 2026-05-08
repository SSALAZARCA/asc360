"""create color_runt_mappings table

Revision ID: h9c0d1e2f3g4
Revises: g8b9c0d1e2f3
Create Date: 2026-05-08
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = 'h9c0d1e2f3g4'
down_revision = 'g8b9c0d1e2f3'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'color_runt_mappings',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('color_key', sa.String(255), nullable=False),
        sa.Column('color_original', sa.String(255), nullable=False),
        sa.Column('codigo_runt', sa.Integer, nullable=True),
        sa.Column('nombre_runt', sa.String(255), nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.text('now()')),
        sa.UniqueConstraint('color_key', name='uq_color_runt_color_key'),
    )

    # Seed con los 15 mapeos conocidos (claves ya normalizadas: UPPER, trim, / → space)
    op.execute("""
        INSERT INTO color_runt_mappings (id, color_key, color_original, codigo_runt, nombre_runt) VALUES
        (gen_random_uuid(), 'ALPINE MAT WHITE',  'ALPINE MAT WHITE',  9251,  'BLANCO MATE'),
        (gen_random_uuid(), 'BAJA MAT SAND',     'BAJA MAT SAND',       80,  'ARENA'),
        (gen_random_uuid(), 'BAJA MATT SAND',    'BAJA MATT SAND',      80,  'ARENA'),
        (gen_random_uuid(), 'BLACK',             'BLACK',               43,  'NEGRO'),
        (gen_random_uuid(), 'BLACK RED',         'BLACK RED',         2338,  'NEGRO ROJO'),
        (gen_random_uuid(), 'BLACK NEON YELLOW', 'Black/Neon Yellow', 17501, 'AMARILLO NEON - NEGRO'),
        (gen_random_uuid(), 'GLOSSY BLACK',      'GLOSSY BLACK',      2255,  'NEGRO BRILLANTE'),
        (gen_random_uuid(), 'GRAY NEON YELLOW',  'GRAY/NEON YELLOW',  15493, 'GRIS AMARILLO NEON'),
        (gen_random_uuid(), 'MATT GRAY',         'MATT GRAY',         10484, 'GRIS MATE'),
        (gen_random_uuid(), 'MATT GREEN',        'MATT GREEN',         7792, 'VERDE MATE'),
        (gen_random_uuid(), 'MATT GREY',         'MATT GREY',         10484, 'GRIS MATE'),
        (gen_random_uuid(), 'MATT SAND',         'MATT SAND',            80, 'ARENA'),
        (gen_random_uuid(), 'MATT WHITE',        'MATT WHITE',         9251, 'BLANCO MATE'),
        (gen_random_uuid(), 'RED',               'RED',                  53, 'ROJO'),
        (gen_random_uuid(), 'WHITE ORANGE',      'WHITE/ORANGE',        181, 'BLANCO NARANJA')
    """)


def downgrade():
    op.drop_table('color_runt_mappings')
