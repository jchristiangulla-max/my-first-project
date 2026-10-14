
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "seven_home.db"

SERVICES = [
    "Home Cleaning",
    "Electrical Services",
    "Plumbing Services",
    "Aircon Cleaning",
    "Pest Control Services",
]


def get_db_connection():
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db():
    with get_db_connection() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                contact_number TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS staff (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS teams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service_type TEXT NOT NULL,
                team_name TEXT NOT NULL,
                availability TEXT NOT NULL DEFAULT 'Available',
                UNIQUE(service_type, team_name)
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL,
                service_type TEXT NOT NULL,
                service_address TEXT NOT NULL,
                preferred_date TEXT NOT NULL,
                preferred_time TEXT NOT NULL,
                additional_notes TEXT,
                status TEXT NOT NULL DEFAULT 'Pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (customer_id) REFERENCES customers(id)
            )
        """)

        # Add new columns safely to an existing bookings table.
        existing_columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(bookings)"
            ).fetchall()
        }

        new_columns = {
            "team_id": "INTEGER REFERENCES teams(id)",
            "cancelled_by": "TEXT",
            "cancellation_reason": "TEXT",
            "cancelled_at": "TIMESTAMP",
        }

        for column_name, column_type in new_columns.items():
            if column_name not in existing_columns:
                connection.execute(
                    f"ALTER TABLE bookings ADD COLUMN "
                    f"{column_name} {column_type}"
                )

        # Create two teams for each service category.
        for service in SERVICES:
            for team_name in ("Team A", "Team B"):
                connection.execute("""
                    INSERT OR IGNORE INTO teams
                    (service_type, team_name, availability)
                    VALUES (?, ?, 'Available')
                """, (service, team_name))


if __name__ == "__main__":
    init_db()
    print("Database and staff tables initialized successfully!")
