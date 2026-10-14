
import getpass
import sqlite3

from werkzeug.security import generate_password_hash
from database import init_db, get_db_connection


def main():
    init_db()

    print("Create a Seven Home Services staff account")
    full_name = input("Staff full name: ").strip()
    email = input("Staff email: ").strip().lower()
    password = getpass.getpass("Create password (8+ characters): ")
    confirm_password = getpass.getpass("Confirm password: ")

    if not full_name or not email:
        print("Name and email are required.")
        return

    if len(password) < 8:
        print("Password must be at least 8 characters.")
        return

    if password != confirm_password:
        print("Passwords do not match.")
        return

    try:
        with get_db_connection() as connection:
            connection.execute("""
                INSERT INTO staff (full_name, email, password_hash)
                VALUES (?, ?, ?)
            """, (
                full_name,
                email,
                generate_password_hash(password)
            ))

        print("Staff account created successfully!")

    except sqlite3.IntegrityError:
        print("That staff email is already registered.")


if __name__ == "__main__":
    main()
