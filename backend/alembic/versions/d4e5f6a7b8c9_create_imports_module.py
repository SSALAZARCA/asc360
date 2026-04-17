"""create imports module tables

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-04-06

Crea las 10 tablas del módulo de importaciones:
  shipment_orders, shipment_moto_units, spare_part_lots, spare_part_items,
  packing_lists, packing_list_items, reconciliation_results,
  backorders, import_attachments, import_audit_log
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = 'd4e5f6a7b8c9'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


def upgrade():
    # ------------------------------------------------------------------ #
    # shipment_orders
    # ------------------------------------------------------------------ #
    op.create_table(
        'shipment_orders',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('cycle', sa.Integer(), nullable=True),
        sa.Column('pi_number', sa.String(100), nullable=False),
        sa.Column('invoice_number', sa.String(100), nullable=True),
        sa.Column('model', sa.String(255), nullable=False),
        sa.Column('model_year', sa.Integer(), nullable=True),
        sa.Column('qty', sa.String(50), nullable=True),
        sa.Column('qty_numeric', sa.Integer(), nullable=True),
        sa.Column('total_units', sa.Integer(), nullable=True),
        sa.Column('containers', sa.Integer(), nullable=True),
        sa.Column('etr', sa.DateTime(), nullable=True),
        sa.Column('etr_raw', sa.String(50), nullable=True),
        sa.Column('etl', sa.DateTime(), nullable=True),
        sa.Column('etl_raw', sa.String(50), nullable=True),
        sa.Column('etd', sa.DateTime(), nullable=True),
        sa.Column('etd_raw', sa.String(50), nullable=True),
        sa.Column('eta', sa.DateTime(), nullable=True),
        sa.Column('eta_raw', sa.String(50), nullable=True),
        sa.Column('departure_port', sa.String(100), nullable=True),
        sa.Column('bl_container', sa.String(255), nullable=True),
        sa.Column('vessel', sa.String(255), nullable=True),
        sa.Column('digital_docs_status', sa.String(50), nullable=True, server_default='PENDING'),
        sa.Column('original_docs_status', sa.String(50), nullable=True, server_default='PENDING'),
        sa.Column('remarks', sa.Text(), nullable=True),
        sa.Column('is_spare_part', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('parent_pi_number', sa.String(100), nullable=True),
        sa.Column('computed_status', sa.String(50), nullable=True, server_default='en_preparacion'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('pi_number', 'model', name='uq_shipment_pi_model'),
    )
    op.create_index('ix_shipment_cycle', 'shipment_orders', ['cycle'])
    op.create_index('ix_shipment_is_spare', 'shipment_orders', ['is_spare_part'])
    op.create_index('ix_shipment_status', 'shipment_orders', ['computed_status'])
    op.create_index('ix_shipment_parent_pi', 'shipment_orders', ['parent_pi_number'])

    # ------------------------------------------------------------------ #
    # shipment_moto_units
    # ------------------------------------------------------------------ #
    op.create_table(
        'shipment_moto_units',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('shipment_order_id', UUID(as_uuid=True), sa.ForeignKey('shipment_orders.id'), nullable=False),
        sa.Column('item_no', sa.Integer(), nullable=True),
        sa.Column('vin_number', sa.String(100), nullable=True),
        sa.Column('engine_number', sa.String(100), nullable=True),
        sa.Column('color', sa.String(100), nullable=True),
        sa.Column('container_no', sa.String(100), nullable=True),
        sa.Column('seal_no', sa.String(100), nullable=True),
        sa.Column('source_pi', sa.String(50), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_moto_unit_vin', 'shipment_moto_units', ['vin_number'])
    op.create_index('ix_moto_unit_order', 'shipment_moto_units', ['shipment_order_id'])

    # ------------------------------------------------------------------ #
    # spare_part_lots
    # ------------------------------------------------------------------ #
    op.create_table(
        'spare_part_lots',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('shipment_order_id', UUID(as_uuid=True), sa.ForeignKey('shipment_orders.id'), nullable=False),
        sa.Column('lot_identifier', sa.String(100), nullable=False, unique=True),
        sa.Column('detail_loaded', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('packing_list_received', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('total_declared_value', sa.Numeric(14, 2), nullable=True),
        sa.Column('currency', sa.String(10), nullable=True, server_default='USD'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_spl_shipment_order', 'spare_part_lots', ['shipment_order_id'])

    # ------------------------------------------------------------------ #
    # spare_part_items
    # ------------------------------------------------------------------ #
    op.create_table(
        'spare_part_items',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('lot_id', UUID(as_uuid=True), sa.ForeignKey('spare_part_lots.id'), nullable=False),
        sa.Column('part_number', sa.String(100), nullable=False),
        sa.Column('description', sa.String(500), nullable=True),
        sa.Column('description_es', sa.String(500), nullable=True),
        sa.Column('model_applicable', sa.String(255), nullable=True),
        sa.Column('qty_cartons', sa.Integer(), nullable=True),
        sa.Column('qty_ordered', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('qty_received', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('qty_pending', sa.Integer(), nullable=True),
        sa.Column('net_weight_kg', sa.Numeric(10, 2), nullable=True),
        sa.Column('gross_weight_kg', sa.Numeric(10, 2), nullable=True),
        sa.Column('cbm', sa.Numeric(10, 4), nullable=True),
        sa.Column('unit_price', sa.Numeric(12, 2), nullable=True),
        sa.Column('amount', sa.Numeric(12, 2), nullable=True),
        sa.Column('status', sa.String(50), nullable=False, server_default='PENDING'),
        sa.Column('backorder_pi', sa.String(100), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_spi_lot', 'spare_part_items', ['lot_id'])
    op.create_index('ix_spi_part_number', 'spare_part_items', ['part_number'])
    op.create_index('ix_spi_status', 'spare_part_items', ['status'])

    # ------------------------------------------------------------------ #
    # packing_lists
    # ------------------------------------------------------------------ #
    op.create_table(
        'packing_lists',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('lot_id', UUID(as_uuid=True), sa.ForeignKey('spare_part_lots.id'), nullable=False),
        sa.Column('uploaded_by', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('file_name', sa.String(500), nullable=False),
        sa.Column('minio_object_name', sa.String(1000), nullable=False),
        sa.Column('uploaded_at', sa.DateTime(), nullable=False),
        sa.Column('processed', sa.Boolean(), nullable=False, server_default='false'),
    )
    op.create_index('ix_pl_lot', 'packing_lists', ['lot_id'])

    # ------------------------------------------------------------------ #
    # packing_list_items
    # ------------------------------------------------------------------ #
    op.create_table(
        'packing_list_items',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('packing_list_id', UUID(as_uuid=True), sa.ForeignKey('packing_lists.id'), nullable=False),
        sa.Column('part_number', sa.String(100), nullable=False),
        sa.Column('description', sa.String(500), nullable=True),
        sa.Column('model', sa.String(255), nullable=True),
        sa.Column('qty', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('unit_price', sa.Numeric(12, 2), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
    )
    op.create_index('ix_pli_packing_list', 'packing_list_items', ['packing_list_id'])
    op.create_index('ix_pli_part_number', 'packing_list_items', ['part_number'])

    # ------------------------------------------------------------------ #
    # reconciliation_results
    # ------------------------------------------------------------------ #
    op.create_table(
        'reconciliation_results',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('lot_id', UUID(as_uuid=True), sa.ForeignKey('spare_part_lots.id'), nullable=False),
        sa.Column('packing_list_id', UUID(as_uuid=True), sa.ForeignKey('packing_lists.id'), nullable=False),
        sa.Column('spare_part_item_id', UUID(as_uuid=True), sa.ForeignKey('spare_part_items.id'), nullable=True),
        sa.Column('part_number', sa.String(100), nullable=False),
        sa.Column('qty_ordered', sa.Integer(), nullable=True),
        sa.Column('qty_in_packing', sa.Integer(), nullable=True),
        sa.Column('result', sa.String(20), nullable=False),
        sa.Column('confirmed_by', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('confirmed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_rr_lot', 'reconciliation_results', ['lot_id'])
    op.create_index('ix_rr_packing_list', 'reconciliation_results', ['packing_list_id'])
    op.create_index('ix_rr_result', 'reconciliation_results', ['result'])

    # ------------------------------------------------------------------ #
    # backorders
    # ------------------------------------------------------------------ #
    op.create_table(
        'backorders',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('spare_part_item_id', UUID(as_uuid=True), sa.ForeignKey('spare_part_items.id'), nullable=False),
        sa.Column('part_number', sa.String(100), nullable=False),
        sa.Column('origin_pi', sa.String(100), nullable=False),
        sa.Column('expected_in_pi', sa.String(100), nullable=True),
        sa.Column('qty_pending', sa.Integer(), nullable=False),
        sa.Column('resolved', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.Column('history', JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_bo_part_number', 'backorders', ['part_number'])
    op.create_index('ix_bo_status', 'backorders', ['resolved'])
    op.create_index('ix_bo_origin_pi', 'backorders', ['origin_pi'])

    # ------------------------------------------------------------------ #
    # import_attachments
    # ------------------------------------------------------------------ #
    op.create_table(
        'import_attachments',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('shipment_order_id', UUID(as_uuid=True), sa.ForeignKey('shipment_orders.id'), nullable=True),
        sa.Column('lot_id', UUID(as_uuid=True), sa.ForeignKey('spare_part_lots.id'), nullable=True),
        sa.Column('uploaded_by', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('file_name', sa.String(500), nullable=False),
        sa.Column('file_type', sa.String(50), nullable=False, server_default='OTHER'),
        sa.Column('minio_object_name', sa.String(1000), nullable=False),
        sa.Column('content_type', sa.String(100), nullable=True),
        sa.Column('uploaded_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_ia_shipment_order', 'import_attachments', ['shipment_order_id'])
    op.create_index('ix_ia_lot', 'import_attachments', ['lot_id'])

    # ------------------------------------------------------------------ #
    # import_audit_log
    # ------------------------------------------------------------------ #
    op.create_table(
        'import_audit_log',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('shipment_order_id', UUID(as_uuid=True), sa.ForeignKey('shipment_orders.id'), nullable=True),
        sa.Column('actor_id', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('actor_role', sa.String(50), nullable=True),
        sa.Column('action', sa.String(100), nullable=False),
        sa.Column('entity_type', sa.String(50), nullable=True),
        sa.Column('entity_id', sa.String(100), nullable=True),
        sa.Column('payload', JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_ial_entity', 'import_audit_log', ['entity_type', 'entity_id'])
    op.create_index('ix_ial_created_at', 'import_audit_log', ['created_at'])


def downgrade():
    op.drop_table('import_audit_log')
    op.drop_table('import_attachments')
    op.drop_table('backorders')
    op.drop_table('reconciliation_results')
    op.drop_table('packing_list_items')
    op.drop_table('packing_lists')
    op.drop_table('spare_part_items')
    op.drop_table('spare_part_lots')
    op.drop_table('shipment_moto_units')
    op.drop_table('shipment_orders')
