"""Shared pytest fixtures for all test modules."""

import pytest


@pytest.fixture
def mock_firestore_client(mocker):
    """Mocked Firestore client for unit tests."""
    # TODO: Configure mock when google-cloud-firestore is installed
    pass


@pytest.fixture
def mock_cloudsql_engine(mocker):
    """Mocked Cloud SQL engine for unit tests."""
    # TODO: Configure mock when sqlalchemy is installed
    pass


@pytest.fixture
def sample_trello_board() -> dict:
    """Returns a sample Trello board payload for testing."""
    return {
        "id": "test-board-001",
        "name": "Engineering Sprint",
        "lists": [
            {"id": "list-1", "name": "To Do"},
            {"id": "list-2", "name": "In Progress"},
            {"id": "list-3", "name": "Done"},
        ],
        "cards": [
            {
                "id": "card-1",
                "name": "Fix login bug",
                "idList": "list-1",
                "labels": [{"name": "Urgent", "color": "red"}],
                "due": "2026-10-15T00:00:00.000Z",
            },
        ],
    }


@pytest.fixture
def sample_expense_event() -> dict:
    """Returns a sample expense webhook payload for testing."""
    return {
        "merchant": "Trello",
        "amount": 120.00,
        "currency": "USD",
        "frequency": "monthly",
        "renewal_date": "2026-11-01",
        "card_last_four": "4242",
    }
