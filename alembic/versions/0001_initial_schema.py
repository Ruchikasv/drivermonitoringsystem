"""Initial migration for Driver Monitoring System multi-tenant schema.

Revision ID: 0001
Revises: 
Create Date: 2026-08-26 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. system_metadata
    op.create_table(
        'system_metadata',
        sa.Column('key', sa.String(length=100), primary_key=True),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
    )

    # 2. owners
    op.create_table(
        'owners',
        sa.Column('owner_id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('name', sa.String(length=150), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False, unique=True),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('is_active', sa.Integer(), server_default='1'),
    )

    # 3. drivers
    op.create_table(
        'drivers',
        sa.Column('driver_id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('name', sa.String(length=150), nullable=False),
        sa.Column('phone', sa.String(length=50), nullable=True),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('license_no', sa.String(length=100), nullable=True),
        sa.Column('face_embedding', sa.LargeBinary(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('is_active', sa.Integer(), server_default='1'),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.Column('owner_id', sa.Integer(), sa.ForeignKey('owners.owner_id', ondelete='CASCADE'), nullable=True),
    )

    # 4. vehicles
    op.create_table(
        'vehicles',
        sa.Column('vehicle_id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('registration_number', sa.String(length=50), nullable=False),
        sa.Column('model', sa.String(length=100), nullable=True),
        sa.Column('vehicle_type', sa.String(length=50), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('is_active', sa.Integer(), server_default='1'),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.Column('owner_id', sa.Integer(), sa.ForeignKey('owners.owner_id', ondelete='CASCADE'), nullable=True),
    )

    # 5. driver_vehicle_assignments
    op.create_table(
        'driver_vehicle_assignments',
        sa.Column('assignment_id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('driver_id', sa.Integer(), sa.ForeignKey('drivers.driver_id', ondelete='CASCADE'), nullable=False),
        sa.Column('vehicle_id', sa.Integer(), sa.ForeignKey('vehicles.vehicle_id', ondelete='CASCADE'), nullable=False),
        sa.Column('assigned_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('unassigned_at', sa.DateTime(), nullable=True),
        sa.Column('owner_id', sa.Integer(), sa.ForeignKey('owners.owner_id', ondelete='CASCADE'), nullable=True),
    )

    # 6. monitoring_sessions
    op.create_table(
        'monitoring_sessions',
        sa.Column('session_id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('driver_id', sa.Integer(), sa.ForeignKey('drivers.driver_id', ondelete='SET NULL'), nullable=True),
        sa.Column('vehicle_id', sa.Integer(), sa.ForeignKey('vehicles.vehicle_id', ondelete='SET NULL'), nullable=True),
        sa.Column('start_time', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('end_time', sa.DateTime(), nullable=True),
        sa.Column('status', sa.String(length=20), server_default='ACTIVE'),
        sa.Column('session_token', sa.String(length=128), nullable=True),
        sa.Column('owner_id', sa.Integer(), sa.ForeignKey('owners.owner_id', ondelete='SET NULL'), nullable=True),
    )

    # 7. monitoring_incidents
    op.create_table(
        'monitoring_incidents',
        sa.Column('incident_id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('session_id', sa.Integer(), sa.ForeignKey('monitoring_sessions.session_id', ondelete='CASCADE'), nullable=False),
        sa.Column('driver_id', sa.Integer(), sa.ForeignKey('drivers.driver_id', ondelete='SET NULL'), nullable=True),
        sa.Column('vehicle_id', sa.Integer(), sa.ForeignKey('vehicles.vehicle_id', ondelete='SET NULL'), nullable=True),
        sa.Column('timestamp', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('event_type', sa.String(length=50), nullable=False),
        sa.Column('alert_level', sa.Integer(), server_default='1'),
        sa.Column('kss_score', sa.Float(), nullable=True),
        sa.Column('ear', sa.Float(), nullable=True),
        sa.Column('mar', sa.Float(), nullable=True),
        sa.Column('perclos', sa.Float(), nullable=True),
        sa.Column('head_pitch_deg', sa.Float(), nullable=True),
        sa.Column('evidence_path', sa.String(length=500), nullable=True),
        sa.Column('owner_id', sa.Integer(), sa.ForeignKey('owners.owner_id', ondelete='SET NULL'), nullable=True),
    )

    # 8. driver_safety_ratings
    op.create_table(
        'driver_safety_ratings',
        sa.Column('driver_id', sa.Integer(), sa.ForeignKey('drivers.driver_id', ondelete='CASCADE'), primary_key=True),
        sa.Column('safety_score', sa.Float(), server_default='100.0'),
        sa.Column('total_sessions', sa.Integer(), server_default='0'),
        sa.Column('total_incidents', sa.Integer(), server_default='0'),
        sa.Column('critical_incidents', sa.Integer(), server_default='0'),
        sa.Column('last_updated', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('owner_id', sa.Integer(), sa.ForeignKey('owners.owner_id', ondelete='CASCADE'), nullable=True),
    )



def downgrade() -> None:
    op.drop_table('driver_safety_ratings')
    op.drop_table('monitoring_incidents')
    op.drop_table('monitoring_sessions')
    op.drop_table('driver_vehicle_assignments')
    op.drop_table('vehicles')
    op.drop_table('drivers')
    op.drop_table('owners')
    op.drop_table('system_metadata')
