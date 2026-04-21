"""add network capabilities and extended fields to tenants

Revision ID: r8n0o1p2q3r4
Revises: q7l8m9n0o1p2
Branch Labels: None
Depends On: None
"""
from alembic import op
import sqlalchemy as sa

revision = 'r8n0o1p2q3r4'
down_revision = 'q7l8m9n0o1p2'
branch_labels = None
depends_on = None


def upgrade():
    # Capacidades de red
    op.add_column('tenants', sa.Column('has_sales', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('tenants', sa.Column('has_parts', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('tenants', sa.Column('has_service', sa.Boolean(), nullable=False, server_default='false'))

    # Identificación extendida
    op.add_column('tenants', sa.Column('representante_legal', sa.String(255), nullable=True))
    op.add_column('tenants', sa.Column('email', sa.String(255), nullable=True))
    op.add_column('tenants', sa.Column('direccion', sa.String(500), nullable=True))
    op.add_column('tenants', sa.Column('zona_geografica', sa.String(100), nullable=True))
    op.add_column('tenants', sa.Column('fecha_vinculacion', sa.Date(), nullable=True))
    op.add_column('tenants', sa.Column('categoria', sa.String(10), nullable=True))

    # Estado de red con enum
    op.execute("CREATE TYPE estadored AS ENUM ('activo', 'suspendido', 'retirado')")
    op.add_column('tenants', sa.Column('estado_red', sa.Enum('activo', 'suspendido', 'retirado', name='estadored'), nullable=False, server_default='activo'))

    # Nuevo valor en TenantType enum
    op.execute("ALTER TYPE tenanttype ADD VALUE IF NOT EXISTS 'distribuidor'")

    # Migrar tenants existentes: service_center → has_service=true
    op.execute("UPDATE tenants SET has_service = true WHERE tenant_type = 'service_center'")
    # parts_dealer → has_parts=true
    op.execute("UPDATE tenants SET has_parts = true WHERE tenant_type = 'parts_dealer'")


def downgrade():
    op.drop_column('tenants', 'has_sales')
    op.drop_column('tenants', 'has_parts')
    op.drop_column('tenants', 'has_service')
    op.drop_column('tenants', 'representante_legal')
    op.drop_column('tenants', 'email')
    op.drop_column('tenants', 'direccion')
    op.drop_column('tenants', 'zona_geografica')
    op.drop_column('tenants', 'fecha_vinculacion')
    op.drop_column('tenants', 'categoria')
    op.drop_column('tenants', 'estado_red')
    op.execute("DROP TYPE IF EXISTS estadored")
