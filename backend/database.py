"""
database.py
------------
Sets up the SQLite database connection and session management
using SQLAlchemy.

This is the ONLY file that knows how/where the database is stored.
Every other file asks this file for a database session.
"""

import os

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from config import settings

DATABASE_URL = settings.database_url

if DATABASE_URL.startswith("sqlite"):
    db_path = DATABASE_URL.replace("sqlite:///", "", 1)
    if db_path.startswith("./"):
        db_path = db_path[2:]
    if db_path and not os.path.isabs(db_path):
        db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), db_path))
    directory = os.path.dirname(db_path)
    if directory:
        os.makedirs(directory, exist_ok=True)

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 30} if DATABASE_URL.startswith("sqlite") else {},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def run_additive_migrations():
    """Add optional columns and indexes without deleting existing records."""
    if not DATABASE_URL.startswith("sqlite"):
        return
    with engine.begin() as connection:
        existing = {column[1] for column in connection.execute(text("PRAGMA table_info(participants)"))}
        for name, definition in {
            "payment_timestamp": "DATETIME",
            "amount_paise": "INTEGER",
            "payment_token_hash": "VARCHAR",
        }.items():
            if name not in existing:
                connection.execute(text(f"ALTER TABLE participants ADD COLUMN {name} {definition}"))
        if "amount" in existing:
            connection.execute(text("UPDATE participants SET amount_paise = CAST(ROUND(amount * 100) AS INTEGER) WHERE amount_paise IS NULL AND amount IS NOT NULL"))
        attempts = {column[1] for column in connection.execute(text("PRAGMA table_info(payment_attempts)"))}
        if attempts and "amount_paise" not in attempts:
            connection.execute(text("ALTER TABLE payment_attempts ADD COLUMN amount_paise INTEGER"))
            if "amount" in attempts:
                connection.execute(text("UPDATE payment_attempts SET amount_paise = amount * 100 WHERE amount_paise IS NULL"))
        connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_participants_payment_id ON participants (razorpay_payment_id) WHERE razorpay_payment_id IS NOT NULL"))
        connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_participants_order_id ON participants (razorpay_order_id) WHERE razorpay_order_id IS NOT NULL"))
        connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_participants_email_workshop_unique ON participants (LOWER(email), workshop)"))
        connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_participants_whatsapp_workshop_unique ON participants (LOWER(whatsapp), workshop)"))


def get_db():
    """
    FastAPI dependency that provides a database session for a single
    request, and guarantees the session is closed afterwards, even if
    an error occurs.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
