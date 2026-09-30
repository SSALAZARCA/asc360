"""login lockout columns and login_evento table

Revision ID: d9a2b6e04f71
Revises: c4e7a19b3d58
Create Date: 2026-09-30 19:00:00.000000

Additive only. `usuario` gets the failed-login counter, its window start and
the lock expiry (`login_fallidos` NOT NULL default 0; the others nullable).
`login_evento` logs every login attempt (EXITO / FALLO / BLOQUEADO).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'd9a2b6e04f71'
down_revision: Union[str, None] = 'c4e7a19b3d58'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("usuario", sa.Column("login_fallidos", sa.Integer(), nullable=False, server_default=sa.text("0")))
    op.add_column("usuario", sa.Column("login_ventana_inicio", sa.DateTime(), nullable=True))
    op.add_column("usuario", sa.Column("bloqueado_hasta", sa.DateTime(), nullable=True))
    op.create_table(
        "login_evento",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("email_intentado", sa.String(length=255), nullable=False),
        sa.Column("usuario_id", sa.UUID(), nullable=True),
        sa.Column("resultado", sa.String(length=16), nullable=False),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.Column("motivo", sa.String(length=32), nullable=True),
        sa.CheckConstraint("resultado IN ('EXITO', 'FALLO', 'BLOQUEADO')", name="ck_login_evento_resultado"),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_login_evento_created_at", "login_evento", [sa.text("created_at DESC")])
    op.create_index("ix_login_evento_usuario_created", "login_evento", ["usuario_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_login_evento_usuario_created", table_name="login_evento")
    op.drop_index("ix_login_evento_created_at", table_name="login_evento")
    op.drop_table("login_evento")
    op.drop_column("usuario", "bloqueado_hasta")
    op.drop_column("usuario", "login_ventana_inicio")
    op.drop_column("usuario", "login_fallidos")
