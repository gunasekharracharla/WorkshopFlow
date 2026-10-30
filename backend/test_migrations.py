import os
import pathlib
import sqlite3
import subprocess
import sys
import tempfile

BACKEND_DIR = pathlib.Path(__file__).resolve().parent


def run_alembic(database_url, revision):
    environment = os.environ.copy()
    environment["DATABASE_URL"] = database_url
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(BACKEND_DIR), environment.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", revision],
        cwd=BACKEND_DIR,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )


def test_legacy_amount_migration_preserves_records_and_converts_to_paise():
    with tempfile.TemporaryDirectory() as tmpdir:
        database_path = pathlib.Path(tmpdir) / "legacy.db"
        database_url = f"sqlite:///{database_path}"
        run_alembic(database_url, "1d5d0d42e5b4")
        connection = sqlite3.connect(database_path)
        connection.execute(
            "INSERT INTO participants (name, email, whatsapp, role, experience, workshop, amount, payment_status, registered_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("Legacy", "legacy@example.com", "+918123456789", "Other", "1", "MNRATHI AI Power Hour", 399, "SUCCESS", "2026-09-22 00:00:00"),
        )
        connection.commit()
        connection.close()

        run_alembic(database_url, "head")
        connection = sqlite3.connect(database_path)
        row = connection.execute(
            "SELECT COUNT(*), amount_paise, workshop FROM participants WHERE email = ?",
            ("legacy@example.com",),
        ).fetchone()
        workshop = connection.execute(
            "SELECT workshop_name, slug FROM workshops WHERE id = 1"
        ).fetchone()
        tables = {name for (name,) in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        connection.close()

        assert row == (1, 39900, "Full-Stack Web Development Workshop")
        assert workshop == ("Full-Stack Web Development Workshop", "full-stack-web-development")
        assert {"payment_attempts", "seat_counters", "webhook_events", "notification_outbox"}.issubset(tables)
