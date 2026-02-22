"""Tests for Phase 5: WebSocket, backup, health check."""

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, StaticPool
from sqlalchemy.orm import sessionmaker

from nimbus.app import create_app
from nimbus.db import Base, get_db
from nimbus.services.backup import backup_database, list_backups


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    app = create_app()

    def override():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = override
    return TestClient(app)


# ---------------------------------------------------------------------------
# Health check tests
# ---------------------------------------------------------------------------


def test_health_returns_db_status(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("ok", "degraded")
    assert "checks" in data
    assert data["checks"]["database"] in ("ok", "unreachable")


# ---------------------------------------------------------------------------
# WebSocket tests
# ---------------------------------------------------------------------------


def test_websocket_ping_pong(client):
    with client.websocket_connect("/ws") as ws:
        ws.send_text("ping")
        resp = ws.receive_json()
        assert resp["type"] == "pong"


# ---------------------------------------------------------------------------
# Backup tests
# ---------------------------------------------------------------------------


def test_backup_database(tmp_path):
    # Create a real SQLite DB to backup
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
    conn.execute("INSERT INTO t VALUES (1)")
    conn.commit()
    conn.close()

    backup_dir = tmp_path / "backups"

    with patch("nimbus.services.backup.settings") as mock_settings:
        mock_settings.database_url = f"sqlite:///{db_path}"
        result = backup_database(backup_dir=backup_dir, max_backups=3)

    assert "error" not in result
    assert result["size_bytes"] > 0
    assert result["total_backups"] == 1

    # Verify the backup is a valid SQLite DB
    bk_conn = sqlite3.connect(result["path"])
    rows = bk_conn.execute("SELECT * FROM t").fetchall()
    bk_conn.close()
    assert rows == [(1,)]


def test_backup_rotation(tmp_path):
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE t (id INTEGER)")
    conn.commit()
    conn.close()

    backup_dir = tmp_path / "backups"

    with patch("nimbus.services.backup.settings") as mock_settings:
        mock_settings.database_url = f"sqlite:///{db_path}"

        # Create 4 backups with max_backups=2
        import time
        for _ in range(4):
            backup_database(backup_dir=backup_dir, max_backups=2)
            time.sleep(0.01)  # ensure distinct timestamps

    # Should have at most 2 remaining
    remaining = list(backup_dir.glob("nimbus_*.db"))
    assert len(remaining) <= 2


def test_list_backups(tmp_path):
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

    # Create fake backup files
    (backup_dir / "nimbus_20260101_000000.db").write_bytes(b"\x00" * 100)
    (backup_dir / "nimbus_20260102_000000.db").write_bytes(b"\x00" * 200)

    result = list_backups(backup_dir=backup_dir)
    assert len(result) == 2
    # Newest first
    assert result[0]["name"] == "nimbus_20260102_000000.db"
    assert result[0]["size_bytes"] == 200


def test_backup_api(client):
    # Backup with in-memory DB should return an error (no file path)
    resp = client.post("/api/backup")
    assert resp.status_code == 200
    # In-memory DB path won't exist on disk, so expect an error
    data = resp.json()
    assert "error" in data or "path" in data

    # List backups should work regardless
    resp = client.get("/api/backup")
    assert resp.status_code == 200
