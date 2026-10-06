"""Cloud SQL client — shared access layer for relational data.

Provides a SQLAlchemy engine connected to Cloud SQL (PostgreSQL)
via the Cloud SQL Python Connector for IAM-based auth.
"""

import os
from typing import Any

from google.cloud.sql.connector import Connector
from sqlalchemy import Engine, create_engine


def get_cloudsql_engine() -> Engine:
    """Returns a SQLAlchemy engine connected to Cloud SQL.

    Uses the Cloud SQL Python Connector for secure, IAM-based
    connections without needing to allowlist IPs.
    """
    connector = Connector()

    def get_conn() -> Any:
        return connector.connect(
            os.environ["CLOUDSQL_CONNECTION_NAME"],
            "pg8000",
            user=os.environ["CLOUDSQL_DB_USER"],
            password=os.environ["CLOUDSQL_DB_PASSWORD"],
            db=os.environ["CLOUDSQL_DB_NAME"],
        )

    engine = create_engine("postgresql+pg8000://", creator=get_conn)
    return engine


def record_scan_in_cloudsql(
    tenant_id: str,
    scan_data: dict[str, Any],
    engine: Engine | None = None,
) -> None:
    """Records an IdP access scan and app inventory into Cloud SQL.

    Uses parameterized queries via SQLAlchemy to prevent SQL injection.
    """
    if engine is None:
        try:
            engine = get_cloudsql_engine()
        except KeyError:
            # When Cloud SQL env vars are not set (e.g. mock unit tests / local dev)
            return

    from sqlalchemy import text

    insert_scan_sql = text(
        """
        INSERT INTO idp_telemetry (scan_id, tenant_id, timestamp, total_scanned, flagged_count)
        VALUES (:scan_id, :tenant_id, :timestamp, :total_scanned, :flagged_count)
        ON CONFLICT (scan_id) DO NOTHING;
        """
    )

    insert_app_sql = text(
        """
        INSERT INTO application_inventory (
            scan_id, tenant_id, app_id, app_name, vendor, total_seats,
            active_seats, inactive_seats, inactive_ratio, is_flagged_inactive
        )
        VALUES (
            :scan_id, :tenant_id, :app_id, :app_name, :vendor, :total_seats,
            :active_seats, :inactive_seats, :inactive_ratio, :is_flagged_inactive
        )
        ON CONFLICT (tenant_id, app_id) DO UPDATE SET
            total_seats = EXCLUDED.total_seats,
            active_seats = EXCLUDED.active_seats,
            inactive_seats = EXCLUDED.inactive_seats,
            inactive_ratio = EXCLUDED.inactive_ratio,
            is_flagged_inactive = EXCLUDED.is_flagged_inactive;
        """
    )

    scan_id = scan_data.get("scan_id", "")
    timestamp = scan_data.get("timestamp", "")
    total_scanned = scan_data.get("total_apps_scanned", 0)
    flagged_count = scan_data.get("flagged_apps_count", 0)

    with engine.begin() as conn:
        conn.execute(
            insert_scan_sql,
            {
                "scan_id": scan_id,
                "tenant_id": tenant_id,
                "timestamp": timestamp,
                "total_scanned": total_scanned,
                "flagged_count": flagged_count,
            },
        )
        for app_record in scan_data.get("apps", []):
            conn.execute(
                insert_app_sql,
                {
                    "scan_id": scan_id,
                    "tenant_id": tenant_id,
                    "app_id": app_record.get("app_id", ""),
                    "app_name": app_record.get("app_name", ""),
                    "vendor": app_record.get("vendor", ""),
                    "total_seats": app_record.get("total_seats", 0),
                    "active_seats": app_record.get("active_seats", 0),
                    "inactive_seats": app_record.get("inactive_seats", 0),
                    "inactive_ratio": app_record.get("inactive_ratio", 0.0),
                    "is_flagged_inactive": app_record.get("is_flagged_inactive", False),
                },
            )


def record_approval_in_cloudsql(
    approval_data: dict[str, Any],
    engine: Engine | None = None,
) -> None:
    """Records human approval grant in Cloud SQL approvals table."""
    if engine is None:
        try:
            engine = get_cloudsql_engine()
        except KeyError:
            return

    from sqlalchemy import text

    insert_approval_sql = text(
        """
        INSERT INTO approvals (
            proposal_id, gate_type, approved, approver_id, approver_email,
            roles, approved_at, expires_at, notes, revoked
        )
        VALUES (
            :proposal_id, :gate_type, :approved, :approver_id, :approver_email,
            :roles, :approved_at, :expires_at, :notes, :revoked
        )
        ON CONFLICT (proposal_id, gate_type) DO UPDATE SET
            approved = EXCLUDED.approved,
            approver_id = EXCLUDED.approver_id,
            approver_email = EXCLUDED.approver_email,
            roles = EXCLUDED.roles,
            approved_at = EXCLUDED.approved_at,
            expires_at = EXCLUDED.expires_at,
            notes = EXCLUDED.notes,
            revoked = EXCLUDED.revoked;
        """
    )

    roles_str = ",".join(approval_data.get("roles", []))
    params = {
        "proposal_id": approval_data.get("proposal_id", ""),
        "gate_type": str(approval_data.get("gate_type", "")),
        "approved": approval_data.get("approved", True),
        "approver_id": approval_data.get("approver_id", ""),
        "approver_email": approval_data.get("approver_email"),
        "roles": roles_str,
        "approved_at": approval_data.get("approved_at"),
        "expires_at": approval_data.get("expires_at"),
        "notes": approval_data.get("notes"),
        "revoked": approval_data.get("revoked", False),
    }

    with engine.begin() as conn:
        conn.execute(insert_approval_sql, params)


def record_revocation_in_cloudsql(
    proposal_id: str,
    revocation_data: dict[str, Any],
    engine: Engine | None = None,
) -> None:
    """Records approval revocation in Cloud SQL."""
    if engine is None:
        try:
            engine = get_cloudsql_engine()
        except KeyError:
            return

    from sqlalchemy import text

    update_revocation_sql = text(
        """
        UPDATE approvals
        SET revoked = TRUE,
            revoked_at = :revoked_at,
            revoked_by = :revoked_by,
            revoke_reason = :revoke_reason
        WHERE proposal_id = :proposal_id;
        """
    )
    params = {
        "proposal_id": proposal_id,
        "revoked_at": revocation_data.get("revoked_at"),
        "revoked_by": revocation_data.get("revoked_by"),
        "revoke_reason": revocation_data.get("revoke_reason"),
    }
    with engine.begin() as conn:
        conn.execute(update_revocation_sql, params)
