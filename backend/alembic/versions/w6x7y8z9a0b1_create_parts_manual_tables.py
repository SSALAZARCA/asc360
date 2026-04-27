"""create parts_manual_sections, parts_manual_items and vehicle_catalog_map

Revision ID: w6x7y8z9a0b1
Revises: v5w6x7y8z9a0
Create Date: 2026-04-26

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = 'w6x7y8z9a0b1'
down_revision = 'v5w6x7y8z9a0'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'parts_manual_sections',
        sa.Column('id',           UUID(as_uuid=True), primary_key=True),
        sa.Column('model_code',   sa.String(100), nullable=False),
        sa.Column('section_code', sa.String(20),  nullable=False),
        sa.Column('section_name', sa.String(255), nullable=False),
        sa.Column('diagram_url',  sa.String(500), nullable=True),
        sa.Column('created_at',   sa.DateTime,    nullable=True),
    )
    op.create_index('ix_parts_manual_sections_model_code', 'parts_manual_sections', ['model_code'])

    op.create_table(
        'parts_manual_items',
        sa.Column('id',                  UUID(as_uuid=True), primary_key=True),
        sa.Column('section_id',          UUID(as_uuid=True),
                  sa.ForeignKey('parts_manual_sections.id', ondelete='CASCADE'), nullable=False),
        sa.Column('order_num',           sa.String(20),  nullable=False),
        sa.Column('factory_part_number', sa.String(100), nullable=False),
        sa.Column('um_part_number',      sa.String(100), nullable=False),
        sa.Column('description',         sa.String(255), nullable=False),
        sa.Column('unit',                sa.String(20),  nullable=True),
        sa.Column('qty',                 sa.Integer,     nullable=True),
    )
    op.create_index('ix_parts_manual_items_factory_part_number', 'parts_manual_items', ['factory_part_number'])
    op.create_index('ix_parts_manual_items_um_part_number',      'parts_manual_items', ['um_part_number'])

    op.create_table(
        'vehicle_catalog_map',
        sa.Column('vehicle_model_pattern', sa.String(200), primary_key=True),
        sa.Column('catalog_model_code',    sa.String(100), nullable=False),
    )
    op.create_index('ix_vehicle_catalog_map_catalog_model_code', 'vehicle_catalog_map', ['catalog_model_code'])


def downgrade():
    op.drop_table('parts_manual_items')
    op.drop_table('parts_manual_sections')
    op.drop_table('vehicle_catalog_map')
