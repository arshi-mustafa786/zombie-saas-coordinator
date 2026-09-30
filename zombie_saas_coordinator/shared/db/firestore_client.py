"""Firestore client — shared access layer for all agents.

Provides a singleton Firestore client configured via environment
variables. All agents use this module to read/write documents.
"""

from google.cloud import firestore


def get_firestore_client() -> firestore.Client:
    """Returns a configured Firestore client.

    Uses Application Default Credentials (ADC) when running on Cloud Run,
    or GOOGLE_APPLICATION_CREDENTIALS locally.
    """
    # TODO: Add connection pooling and error handling
    return firestore.Client()
