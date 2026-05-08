"""add color_runt to shipment_moto_units

Revision ID: g8b9c0d1e2f3
Revises: f7a8b9c0d1e2
Create Date: 2026-05-08
"""
from alembic import op
import sqlalchemy as sa

revision = 'g8b9c0d1e2f3'
down_revision = 'f7a8b9c0d1e2'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'shipment_moto_units',
        sa.Column('color_runt', sa.String(255), nullable=True)
    )

    # Backfill: poblar color_runt para unidades existentes según tabla RUNT
    op.execute("""
        UPDATE shipment_moto_units
        SET color_runt = CASE
            WHEN UPPER(TRIM(REPLACE(color, '/', ' '))) = 'ALPINE MAT WHITE'   THEN 'BLANCO MATE'
            WHEN UPPER(TRIM(REPLACE(color, '/', ' '))) = 'BAJA MAT SAND'      THEN 'ARENA'
            WHEN UPPER(TRIM(REPLACE(color, '/', ' '))) = 'BAJA MATT SAND'     THEN 'ARENA'
            WHEN UPPER(TRIM(REPLACE(color, '/', ' '))) = 'BLACK'              THEN 'NEGRO'
            WHEN UPPER(TRIM(REPLACE(color, '/', ' '))) = 'BLACK RED'          THEN 'NEGRO ROJO'
            WHEN UPPER(TRIM(REPLACE(color, '/', ' '))) = 'BLACK NEON YELLOW'  THEN 'AMARILLO NEON - NEGRO'
            WHEN UPPER(TRIM(REPLACE(color, '/', ' '))) = 'GLOSSY BLACK'       THEN 'NEGRO BRILLANTE'
            WHEN UPPER(TRIM(REPLACE(color, '/', ' '))) = 'GRAY NEON YELLOW'   THEN 'GRIS AMARILLO NEON'
            WHEN UPPER(TRIM(REPLACE(color, '/', ' '))) = 'MATT GRAY'          THEN 'GRIS MATE'
            WHEN UPPER(TRIM(REPLACE(color, '/', ' '))) = 'MATT GREEN'         THEN 'VERDE MATE'
            WHEN UPPER(TRIM(REPLACE(color, '/', ' '))) = 'MATT GREY'          THEN 'GRIS MATE'
            WHEN UPPER(TRIM(REPLACE(color, '/', ' '))) = 'MATT SAND'          THEN 'ARENA'
            WHEN UPPER(TRIM(REPLACE(color, '/', ' '))) = 'MATT WHITE'         THEN 'BLANCO MATE'
            WHEN UPPER(TRIM(REPLACE(color, '/', ' '))) = 'RED'                THEN 'ROJO'
            WHEN UPPER(TRIM(REPLACE(color, '/', ' '))) = 'WHITE ORANGE'       THEN 'BLANCO NARANJA'
        END
        WHERE color IS NOT NULL
          AND UPPER(TRIM(REPLACE(color, '/', ' '))) IN (
            'ALPINE MAT WHITE', 'BAJA MAT SAND', 'BAJA MATT SAND',
            'BLACK', 'BLACK RED', 'BLACK NEON YELLOW', 'GLOSSY BLACK',
            'GRAY NEON YELLOW', 'MATT GRAY', 'MATT GREEN', 'MATT GREY',
            'MATT SAND', 'MATT WHITE', 'RED', 'WHITE ORANGE'
          );
    """)


def downgrade():
    op.drop_column('shipment_moto_units', 'color_runt')
