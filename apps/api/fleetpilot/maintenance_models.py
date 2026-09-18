"""Maintenance mappings. Migration owns forced RLS and workflow triggers."""

import sqlalchemy as sa

from .models import Base


class MaintenanceSchedule(Base):
    __table__ = sa.Table(
        "maintenance_schedules",
        Base.metadata,
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("organization_id", sa.UUID(), primary_key=False, nullable=False),
        sa.Column("vehicle_id", sa.UUID(), primary_key=False, nullable=False),
        sa.Column("service_type", sa.VARCHAR(length=40), primary_key=False, nullable=False),
        sa.Column("interval_type", sa.VARCHAR(length=30), primary_key=False, nullable=False),
        sa.Column("odometer_interval_km", sa.INTEGER(), primary_key=False, nullable=True),
        sa.Column("date_interval_days", sa.INTEGER(), primary_key=False, nullable=True),
        sa.Column(
            "last_service_odometer",
            sa.NUMERIC(precision=9, scale=1),
            primary_key=False,
            nullable=True,
        ),
        sa.Column("last_service_at", sa.DATE(), primary_key=False, nullable=True),
        sa.Column(
            "next_due_odometer", sa.NUMERIC(precision=12, scale=1), primary_key=False, nullable=True
        ),
        sa.Column("next_due_at", sa.DATE(), primary_key=False, nullable=True),
        sa.Column("warning_km", sa.INTEGER(), primary_key=False, nullable=False),
        sa.Column("warning_days", sa.INTEGER(), primary_key=False, nullable=False),
        sa.Column(
            "is_active",
            sa.BOOLEAN(),
            primary_key=False,
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("notes", sa.TEXT(), primary_key=False, nullable=True),
        sa.Column("created_by", sa.UUID(), primary_key=False, nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            primary_key=False,
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            primary_key=False,
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name="maintenance_schedules_created_by_fkey"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="maintenance_schedules_organization_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "vehicle_id"],
            ["vehicles.organization_id", "vehicles.id"],
            name="maintenance_schedules_organization_id_vehicle_id_fkey",
        ),
        sa.UniqueConstraint(
            *["organization_id", "id"], name="maintenance_schedules_organization_id_id_key"
        ),
        sa.CheckConstraint(
            "(interval_type::text = 'DATE'::text) = (odometer_interval_km IS NULL)",
            name="maintenance_schedules_check",
        ),
        sa.CheckConstraint(
            "(interval_type::text = 'ODOMETER'::text) = (date_interval_days IS NULL)",
            name="maintenance_schedules_check1",
        ),
        sa.CheckConstraint(
            "odometer_interval_km IS NULL OR last_service_odometer IS NOT NULL AND next_due_odometer = (last_service_odometer + odometer_interval_km::numeric) AND warning_km <= odometer_interval_km",
            name="maintenance_schedules_check2",
        ),
        sa.CheckConstraint(
            "date_interval_days IS NULL OR last_service_at IS NOT NULL AND next_due_at = (last_service_at + date_interval_days) AND warning_days <= date_interval_days",
            name="maintenance_schedules_check3",
        ),
        sa.CheckConstraint(
            "date_interval_days >= 1 AND date_interval_days <= 3650",
            name="maintenance_schedules_date_interval_days_check",
        ),
        sa.CheckConstraint(
            "interval_type::text = ANY (ARRAY['ODOMETER'::character varying, 'DATE'::character varying, 'ODOMETER_OR_DATE'::character varying]::text[])",
            name="maintenance_schedules_interval_type_check",
        ),
        sa.CheckConstraint(
            "odometer_interval_km >= 1 AND odometer_interval_km <= 1000000",
            name="maintenance_schedules_odometer_interval_km_check",
        ),
        sa.CheckConstraint("warning_days >= 0", name="maintenance_schedules_warning_days_check"),
        sa.CheckConstraint("warning_km >= 0", name="maintenance_schedules_warning_km_check"),
        sa.Index(
            "ix_maintenance_schedules_lookup",
            *["organization_id", "vehicle_id", "is_active", "next_due_at"],
            unique=False,
        ),
    )


class MaintenanceWorkOrder(Base):
    __table__ = sa.Table(
        "maintenance_work_orders",
        Base.metadata,
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("organization_id", sa.UUID(), primary_key=False, nullable=False),
        sa.Column("vehicle_id", sa.UUID(), primary_key=False, nullable=False),
        sa.Column("maintenance_schedule_id", sa.UUID(), primary_key=False, nullable=True),
        sa.Column("defect_report_id", sa.UUID(), primary_key=False, nullable=True),
        sa.Column("trip_id", sa.UUID(), primary_key=False, nullable=True),
        sa.Column("work_order_number", sa.VARCHAR(length=40), primary_key=False, nullable=False),
        sa.Column("type", sa.VARCHAR(length=30), primary_key=False, nullable=False),
        sa.Column("priority", sa.VARCHAR(length=20), primary_key=False, nullable=False),
        sa.Column(
            "status",
            sa.VARCHAR(length=20),
            primary_key=False,
            nullable=False,
            server_default=sa.text("'OPEN'::character varying"),
        ),
        sa.Column(
            "version", sa.INTEGER(), primary_key=False, nullable=False, server_default=sa.text("1")
        ),
        sa.Column("title", sa.VARCHAR(length=160), primary_key=False, nullable=False),
        sa.Column("description", sa.TEXT(), primary_key=False, nullable=False),
        sa.Column("requires_vehicle_downtime", sa.BOOLEAN(), primary_key=False, nullable=False),
        sa.Column("service_provider", sa.VARCHAR(length=160), primary_key=False, nullable=True),
        sa.Column(
            "opened_at",
            sa.TIMESTAMP(timezone=True),
            primary_key=False,
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.Column("scheduled_at", sa.TIMESTAMP(timezone=True), primary_key=False, nullable=True),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), primary_key=False, nullable=True),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), primary_key=False, nullable=True),
        sa.Column(
            "odometer_at_open", sa.NUMERIC(precision=9, scale=1), primary_key=False, nullable=True
        ),
        sa.Column(
            "odometer_at_completion",
            sa.NUMERIC(precision=9, scale=1),
            primary_key=False,
            nullable=True,
        ),
        sa.Column("work_performed", sa.TEXT(), primary_key=False, nullable=True),
        sa.Column(
            "downtime_started_at", sa.TIMESTAMP(timezone=True), primary_key=False, nullable=True
        ),
        sa.Column(
            "downtime_ended_at", sa.TIMESTAMP(timezone=True), primary_key=False, nullable=True
        ),
        sa.Column("created_by", sa.UUID(), primary_key=False, nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            primary_key=False,
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            primary_key=False,
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name="maintenance_work_orders_created_by_fkey"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "defect_report_id"],
            ["driver_defects.organization_id", "driver_defects.id"],
            name="maintenance_work_orders_organization_id_defect_report_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="maintenance_work_orders_organization_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "maintenance_schedule_id"],
            ["maintenance_schedules.organization_id", "maintenance_schedules.id"],
            name="maintenance_work_orders_organization_id_maintenance_schedu_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "trip_id"],
            ["trips.organization_id", "trips.id"],
            name="maintenance_work_orders_organization_id_trip_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "vehicle_id"],
            ["vehicles.organization_id", "vehicles.id"],
            name="maintenance_work_orders_organization_id_vehicle_id_fkey",
        ),
        sa.UniqueConstraint(
            *["organization_id", "defect_report_id"],
            name="maintenance_work_orders_organization_id_defect_report_id_key",
        ),
        sa.UniqueConstraint(
            *["organization_id", "id"], name="maintenance_work_orders_organization_id_id_key"
        ),
        sa.UniqueConstraint(
            *["organization_id", "work_order_number"],
            name="maintenance_work_orders_organization_id_work_order_number_key",
        ),
        sa.CheckConstraint(
            "downtime_ended_at IS NULL OR downtime_ended_at >= downtime_started_at",
            name="maintenance_work_orders_check",
        ),
        sa.CheckConstraint(
            "(status::text = 'COMPLETED'::text) = (completed_at IS NOT NULL)",
            name="maintenance_work_orders_check1",
        ),
        sa.CheckConstraint(
            "priority::text = ANY (ARRAY['LOW'::character varying, 'NORMAL'::character varying, 'HIGH'::character varying, 'CRITICAL'::character varying]::text[])",
            name="maintenance_work_orders_priority_check",
        ),
        sa.CheckConstraint(
            "status::text = ANY (ARRAY['OPEN'::character varying, 'SCHEDULED'::character varying, 'IN_PROGRESS'::character varying, 'COMPLETED'::character varying, 'CANCELLED'::character varying]::text[])",
            name="maintenance_work_orders_status_check",
        ),
        sa.CheckConstraint(
            "type::text = ANY (ARRAY['PREVENTIVE'::character varying, 'REPAIR'::character varying, 'INSPECTION'::character varying, 'DEFECT_RESPONSE'::character varying, 'OTHER'::character varying]::text[])",
            name="maintenance_work_orders_type_check",
        ),
        sa.Index(
            "ix_maintenance_work_orders_lookup",
            *["organization_id", "vehicle_id", "status", "created_at"],
            unique=False,
        ),
    )


class DriverDefectReport(Base):
    __table__ = sa.Table(
        "driver_defects",
        Base.metadata,
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("organization_id", sa.UUID(), primary_key=False, nullable=False),
        sa.Column("vehicle_id", sa.UUID(), primary_key=False, nullable=False),
        sa.Column("driver_id", sa.UUID(), primary_key=False, nullable=False),
        sa.Column("trip_id", sa.UUID(), primary_key=False, nullable=True),
        sa.Column("severity", sa.VARCHAR(length=20), primary_key=False, nullable=False),
        sa.Column("category", sa.VARCHAR(length=40), primary_key=False, nullable=False),
        sa.Column("description", sa.TEXT(), primary_key=False, nullable=False),
        sa.Column(
            "reported_at_client", sa.TIMESTAMP(timezone=True), primary_key=False, nullable=False
        ),
        sa.Column(
            "received_at_server",
            sa.TIMESTAMP(timezone=True),
            primary_key=False,
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.Column(
            "status",
            sa.VARCHAR(length=30),
            primary_key=False,
            nullable=False,
            server_default=sa.text("'REPORTED'::character varying"),
        ),
        sa.Column("created_by", sa.UUID(), primary_key=False, nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            primary_key=False,
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name="driver_defects_created_by_fkey"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "driver_id"],
            ["drivers.organization_id", "drivers.id"],
            name="driver_defects_organization_id_driver_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], name="driver_defects_organization_id_fkey"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "trip_id"],
            ["trips.organization_id", "trips.id"],
            name="driver_defects_organization_id_trip_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "vehicle_id"],
            ["vehicles.organization_id", "vehicles.id"],
            name="driver_defects_organization_id_vehicle_id_fkey",
        ),
        sa.UniqueConstraint(
            *["organization_id", "id"], name="driver_defects_organization_id_id_key"
        ),
        sa.CheckConstraint(
            "length(TRIM(BOTH FROM description)) >= 3", name="driver_defects_description_check"
        ),
        sa.CheckConstraint(
            "severity::text = ANY (ARRAY['MINOR'::character varying, 'MODERATE'::character varying, 'SERIOUS'::character varying, 'CRITICAL'::character varying]::text[])",
            name="driver_defects_severity_check",
        ),
        sa.CheckConstraint(
            "status::text = ANY (ARRAY['REPORTED'::character varying, 'REVIEWED'::character varying, 'WORK_ORDER_CREATED'::character varying, 'RESOLVED'::character varying, 'DISMISSED'::character varying]::text[])",
            name="driver_defects_status_check",
        ),
        sa.Index(
            "ix_driver_defects_lookup",
            *["organization_id", "vehicle_id", "status", "created_at"],
            unique=False,
        ),
    )


class MaintenanceCostItem(Base):
    __table__ = sa.Table(
        "maintenance_cost_items",
        Base.metadata,
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("organization_id", sa.UUID(), primary_key=False, nullable=False),
        sa.Column("work_order_id", sa.UUID(), primary_key=False, nullable=False),
        sa.Column("type", sa.VARCHAR(length=10), primary_key=False, nullable=False),
        sa.Column("description", sa.TEXT(), primary_key=False, nullable=False),
        sa.Column("quantity", sa.NUMERIC(precision=9, scale=3), primary_key=False, nullable=False),
        sa.Column(
            "unit_cost", sa.NUMERIC(precision=12, scale=4), primary_key=False, nullable=False
        ),
        sa.Column(
            "total_cost", sa.NUMERIC(precision=12, scale=2), primary_key=False, nullable=False
        ),
        sa.Column("vendor", sa.VARCHAR(length=160), primary_key=False, nullable=True),
        sa.Column("reference", sa.VARCHAR(length=120), primary_key=False, nullable=True),
        sa.Column("created_by", sa.UUID(), primary_key=False, nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            primary_key=False,
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name="maintenance_cost_items_created_by_fkey"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="maintenance_cost_items_organization_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "work_order_id"],
            ["maintenance_work_orders.organization_id", "maintenance_work_orders.id"],
            name="maintenance_cost_items_organization_id_work_order_id_fkey",
        ),
        sa.UniqueConstraint(
            *["organization_id", "id"], name="maintenance_cost_items_organization_id_id_key"
        ),
        sa.CheckConstraint(
            "total_cost = round(quantity * unit_cost, 2) AND total_cost >= 0::numeric AND total_cost <= 10000000::numeric",
            name="maintenance_cost_items_check",
        ),
        sa.CheckConstraint("quantity > 0::numeric", name="maintenance_cost_items_quantity_check"),
        sa.CheckConstraint(
            "type::text = ANY (ARRAY['PART'::character varying, 'LABOR'::character varying, 'OTHER'::character varying]::text[])",
            name="maintenance_cost_items_type_check",
        ),
        sa.CheckConstraint(
            "unit_cost >= 0::numeric", name="maintenance_cost_items_unit_cost_check"
        ),
        sa.Index(
            "ix_maintenance_cost_items_lookup",
            *["organization_id", "work_order_id", "created_at"],
            unique=False,
        ),
    )


class MaintenanceEvidence(Base):
    __table__ = sa.Table(
        "maintenance_evidence",
        Base.metadata,
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("organization_id", sa.UUID(), primary_key=False, nullable=False),
        sa.Column("work_order_id", sa.UUID(), primary_key=False, nullable=True),
        sa.Column("defect_id", sa.UUID(), primary_key=False, nullable=True),
        sa.Column("evidence_type", sa.VARCHAR(length=40), primary_key=False, nullable=False),
        sa.Column("storage_key", sa.VARCHAR(length=160), primary_key=False, nullable=False),
        sa.Column("original_filename", sa.VARCHAR(length=160), primary_key=False, nullable=False),
        sa.Column(
            "content_type",
            sa.VARCHAR(length=40),
            primary_key=False,
            nullable=False,
            server_default=sa.text("'image/png'::character varying"),
        ),
        sa.Column("file_size", sa.INTEGER(), primary_key=False, nullable=False),
        sa.Column("checksum", sa.VARCHAR(length=64), primary_key=False, nullable=False),
        sa.Column(
            "status",
            sa.VARCHAR(length=20),
            primary_key=False,
            nullable=False,
            server_default=sa.text("'ACTIVE'::character varying"),
        ),
        sa.Column("uploaded_by", sa.UUID(), primary_key=False, nullable=False),
        sa.Column(
            "uploaded_at",
            sa.TIMESTAMP(timezone=True),
            primary_key=False,
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "defect_id"],
            ["driver_defects.organization_id", "driver_defects.id"],
            name="maintenance_evidence_organization_id_defect_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="maintenance_evidence_organization_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "work_order_id"],
            ["maintenance_work_orders.organization_id", "maintenance_work_orders.id"],
            name="maintenance_evidence_organization_id_work_order_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by"], ["users.id"], name="maintenance_evidence_uploaded_by_fkey"
        ),
        sa.UniqueConstraint(
            *["organization_id", "id"], name="maintenance_evidence_organization_id_id_key"
        ),
        sa.UniqueConstraint(*["storage_key"], name="maintenance_evidence_storage_key_key"),
        sa.CheckConstraint(
            "(work_order_id IS NULL) <> (defect_id IS NULL)", name="maintenance_evidence_check"
        ),
        sa.CheckConstraint(
            "file_size >= 1 AND file_size <= 5242880", name="maintenance_evidence_file_size_check"
        ),
        sa.CheckConstraint(
            "status::text = 'ACTIVE'::text", name="maintenance_evidence_status_check"
        ),
        sa.Index(
            "ix_maintenance_evidence_lookup",
            *["organization_id", "defect_id", "work_order_id"],
            unique=False,
        ),
    )


class MaintenanceEvent(Base):
    __table__ = sa.Table(
        "maintenance_events",
        Base.metadata,
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("organization_id", sa.UUID(), primary_key=False, nullable=False),
        sa.Column("vehicle_id", sa.UUID(), primary_key=False, nullable=False),
        sa.Column("work_order_id", sa.UUID(), primary_key=False, nullable=True),
        sa.Column("defect_id", sa.UUID(), primary_key=False, nullable=True),
        sa.Column("schedule_id", sa.UUID(), primary_key=False, nullable=True),
        sa.Column("action", sa.VARCHAR(length=60), primary_key=False, nullable=False),
        sa.Column("notes", sa.TEXT(), primary_key=False, nullable=True),
        sa.Column("actor_id", sa.UUID(), primary_key=False, nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            primary_key=False,
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["users.id"], name="maintenance_events_actor_id_fkey"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "defect_id"],
            ["driver_defects.organization_id", "driver_defects.id"],
            name="maintenance_events_organization_id_defect_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="maintenance_events_organization_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "schedule_id"],
            ["maintenance_schedules.organization_id", "maintenance_schedules.id"],
            name="maintenance_events_organization_id_schedule_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "vehicle_id"],
            ["vehicles.organization_id", "vehicles.id"],
            name="maintenance_events_organization_id_vehicle_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "work_order_id"],
            ["maintenance_work_orders.organization_id", "maintenance_work_orders.id"],
            name="maintenance_events_organization_id_work_order_id_fkey",
        ),
        sa.Index(
            "ix_maintenance_events_lookup",
            *["organization_id", "vehicle_id", "created_at"],
            unique=False,
        ),
    )
