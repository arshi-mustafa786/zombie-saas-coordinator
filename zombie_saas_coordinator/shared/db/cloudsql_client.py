"""Cloud SQL client — shared access layer for relational data.

Provides a SQLAlchemy engine connected to Cloud SQL (PostgreSQL)
via the Cloud SQL Python Connector for IAM-based auth.
"""

import os

from google.cloud.sql.connector import Connector
from sqlalchemy import create_engine, Engine


def get_cloudsql_engine() -> Engine:
    """Returns a SQLAlchemy engine connected to Cloud SQL.

    Uses the Cloud SQL Python Connector for secure, IAM-based
    connections without needing to allowlist IPs.
    """
    connector = Connector()

    def get_conn():
        return connector.connect(
            os.environ["CLOUDSQL_CONNECTION_NAME"],
            "pg8000",
            user=os.environ["CLOUDSQL_DB_USER"],
            password=os.environ["CLOUDSQL_DB_PASSWORD"],
            db=os.environ["CLOUDSQL_DB_NAME"],
        )

    engine = create_engine("postgresql+pg8000://", creator=get_conn)
    return engine
