"""Firestore client — shared access layer for all agents.

Provides a singleton Firestore client configured via environment
variables. All agents use this module to read/write documents.
"""

import os

from google.cloud import firestore


def get_firestore_client() -> firestore.Client:
    """Returns a configured Firestore client.

    Uses Application Default Credentials (ADC) when running on Cloud Run,
    or GOOGLE_APPLICATION_CREDENTIALS locally.
    """
    database = os.getenv("FIRESTORE_DATABASE_ID") or None
    project = os.getenv("GOOGLE_CLOUD_PROJECT") or None
    return firestore.Client(project=project, database=database)
