from datetime import date, datetime
import os
import sqlite3

from flask import (
    Flask, render_template, request,
    redirect, url_for, flash, session
)
from werkzeug.security import generate_password_hash, check_password_hash

from database import init_db, get_db_connection


app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY", "dev-only-change-before-deployment"
)

init_db()

SERVICES = [
    "Home Cleaning",
    "Electrical Services",
    "Plumbing Services",
    "Aircon Cleaning",
    "Pest Control Services",
]

OPENING_TIME = "08:00"
CLOSING_TIME = "17:00"


# -------------------------
# AUTHENTICATION HELPERS
# -------------------------
def staff_required():
    if "staff_id" not in session:
        flash("Please log in with a staff account.", "warning")
        return False
    return True


def customer_required():
    if "customer_id" not in session:
        flash("Please log in first.", "warning")
        return False
    return True


# -------------------------
# HOME
# -------------------------
@app.route("/")
def home():
    return render_template("index.html")


# -------------------------
# CUSTOMER REGISTRATION
# -------------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        contact_number = request.form.get("contact_number", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not all([
            first_name, last_name, email,
            contact_number, password, confirm_password
        ]):
            flash("Please complete all fields.", "danger")
            return redirect(url_for("register"))

        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return redirect(url_for("register"))

        if len(password) < 8:
            flash("Password must be at least 8 characters.", "danger")
            return redirect(url_for("register"))

        try:
            with get_db_connection() as connection:
                connection.execute("""
                    INSERT INTO customers (
                        first_name, last_name, email,
                        contact_number, password_hash
                    )
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    first_name,
                    last_name,
                    email,
                    contact_number,
                    generate_password_hash(password)
                ))
        except sqlite3.IntegrityError:
            flash("That email is already registered.", "danger")
            return redirect(url_for("register"))

        flash("Registration successful! You can now log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


# -------------------------
# CUSTOMER LOGIN
# -------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        with get_db_connection() as connection:
            customer = connection.execute(
                "SELECT * FROM customers WHERE email = ?",
                (email,)
            ).fetchone()

        if customer and check_password_hash(
            customer["password_hash"], password
        ):
            session.clear()
            session["customer_id"] = customer["id"]
            session["customer_name"] = customer["first_name"]
            return redirect(url_for("dashboard"))

        flash("Invalid email or password.", "danger")

    return render_template("login.html")


# -------------------------
# STAFF LOGIN
# -------------------------
@app.route("/staff/login", methods=["GET", "POST"])
def staff_login():
    if "staff_id" in session:
        return redirect(url_for("staff_dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        with get_db_connection() as connection:
            staff = connection.execute(
                "SELECT * FROM staff WHERE email = ?",
                (email,)
            ).fetchone()

        if staff and check_password_hash(
            staff["password_hash"], password
        ):
            session.clear()
            session["staff_id"] = staff["id"]
            session["staff_name"] = staff["full_name"]
            return redirect(url_for("staff_dashboard"))

        flash("Invalid staff email or password.", "danger")

    return render_template("staff_login.html")


# -------------------------
# STAFF DASHBOARD
# -------------------------
@app.route("/staff/dashboard")
def staff_dashboard():
    if not staff_required():
        return redirect(url_for("staff_login"))

    with get_db_connection() as connection:
        counts = connection.execute("""
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN status = 'Pending' THEN 1 ELSE 0 END) AS pending,
                SUM(CASE WHEN status = 'Approved' THEN 1 ELSE 0 END) AS approved,
                SUM(CASE WHEN status = 'In Progress' THEN 1 ELSE 0 END) AS in_progress,
                SUM(CASE WHEN status = 'Completed' THEN 1 ELSE 0 END) AS completed,
                SUM(CASE WHEN status = 'Cancelled' THEN 1 ELSE 0 END) AS cancelled
            FROM bookings
        """).fetchone()

        bookings = connection.execute("""
            SELECT
                b.*,
                c.first_name,
                c.last_name,
                c.email AS customer_email,
                c.contact_number,
                t.team_name
            FROM bookings AS b
            LEFT JOIN customers AS c ON c.id = b.customer_id
            LEFT JOIN teams AS t ON t.id = b.team_id
            ORDER BY
                CASE WHEN b.status = 'Pending' THEN 0 ELSE 1 END,
                b.preferred_date ASC,
                b.preferred_time ASC,
                b.id DESC
        """).fetchall()

        teams = connection.execute("""
            SELECT id, service_type, team_name
            FROM teams
            ORDER BY service_type, team_name
        """).fetchall()

    return render_template(
        "staff_dashboard.html",
        counts=counts,
        bookings=bookings,
        teams=teams
    )


# -------------------------
# STAFF APPROVES BOOKING
# AND ASSIGNS A TEAM
# -------------------------
@app.route(
    "/staff/booking/<int:booking_id>/approve",
    methods=["POST"]
)
def approve_booking(booking_id):
    if not staff_required():
        return redirect(url_for("staff_login"))

    team_id = request.form.get("team_id", type=int)

    if not team_id:
        flash("Please select a team.", "danger")
        return redirect(url_for("staff_dashboard"))

    with get_db_connection() as connection:
        booking = connection.execute(
            "SELECT * FROM bookings WHERE id = ?",
            (booking_id,)
        ).fetchone()

        team = connection.execute(
            "SELECT * FROM teams WHERE id = ?",
            (team_id,)
        ).fetchone()

        if not booking:
            flash("Booking not found.", "danger")
            return redirect(url_for("staff_dashboard"))

        if booking["status"] != "Pending":
            flash(
                "Only pending bookings can be approved.",
                "warning"
            )
            return redirect(url_for("staff_dashboard"))

        if (
            not team
            or team["service_type"] != booking["service_type"]
        ):
            flash(
                "Please select a valid team for this service.",
                "danger"
            )
            return redirect(url_for("staff_dashboard"))

        if booking["preferred_date"] < date.today().isoformat():
            flash("This booking date has already passed.", "danger")
            return redirect(url_for("staff_dashboard"))

        # Basic conflict check: same team, date, and exact start time.
        conflict = connection.execute("""
            SELECT id
            FROM bookings
            WHERE team_id = ?
              AND preferred_date = ?
              AND preferred_time = ?
              AND status IN ('Approved', 'In Progress')
              AND id != ?
            LIMIT 1
        """, (
            team_id,
            booking["preferred_date"],
            booking["preferred_time"],
            booking_id
        )).fetchone()

        if conflict:
            flash(
                "That team already has a booking at the same date "
                "and time. Choose another team or schedule.",
                "danger"
            )
            return redirect(url_for("staff_dashboard"))

        connection.execute("""
            UPDATE bookings
            SET status = 'Approved',
                team_id = ?
            WHERE id = ? AND status = 'Pending'
        """, (team_id, booking_id))

    flash(
        "Booking approved and team assigned successfully.",
        "success"
    )
    return redirect(url_for("staff_dashboard"))


# -------------------------
# STAFF UPDATES BOOKING STATUS
# -------------------------
@app.route(
    "/staff/booking/<int:booking_id>/status",
    methods=["POST"]
)
def update_booking_status(booking_id):
    if not staff_required():
        return redirect(url_for("staff_login"))

    new_status = request.form.get("status", "").strip()

    allowed_transitions = {
        "Approved": ["In Progress"],
        "In Progress": ["Completed"],
    }

    with get_db_connection() as connection:
        booking = connection.execute(
            "SELECT * FROM bookings WHERE id = ?",
            (booking_id,)
        ).fetchone()

        if not booking:
            flash("Booking not found.", "danger")
            return redirect(url_for("staff_dashboard"))

        allowed = allowed_transitions.get(booking["status"], [])

        if new_status not in allowed:
            flash("That status change is not allowed.", "danger")
            return redirect(url_for("staff_dashboard"))

        connection.execute("""
            UPDATE bookings
            SET status = ?
            WHERE id = ? AND status = ?
        """, (
            new_status,
            booking_id,
            booking["status"]
        ))

    flash(f"Booking status updated to {new_status}.", "success")
    return redirect(url_for("staff_dashboard"))


# -------------------------
# STAFF CANCELS BOOKING
# -------------------------
@app.route(
    "/staff/booking/<int:booking_id>/cancel",
    methods=["POST"]
)
def cancel_booking(booking_id):
    if not staff_required():
        return redirect(url_for("staff_login"))

    reason = request.form.get("reason", "").strip()
    allowed_reasons = {
        "Unable to Contact",
        "Customer Requested",
        "Other",
    }

    if reason not in allowed_reasons:
        flash("Please select a valid cancellation reason.", "danger")
        return redirect(url_for("staff_dashboard"))

    with get_db_connection() as connection:
        booking = connection.execute(
            "SELECT * FROM bookings WHERE id = ?",
            (booking_id,)
        ).fetchone()

        if not booking:
            flash("Booking not found.", "danger")
            return redirect(url_for("staff_dashboard"))

        if booking["status"] not in ("Pending", "Approved"):
            flash(
                "Only pending or approved bookings can be cancelled.",
                "warning"
            )
            return redirect(url_for("staff_dashboard"))

        connection.execute("""
            UPDATE bookings
            SET status = 'Cancelled',
                cancelled_by = ?,
                cancellation_reason = ?,
                cancelled_at = CURRENT_TIMESTAMP
            WHERE id = ?
              AND status IN ('Pending', 'Approved')
        """, (
            f"Staff: {session['staff_name']}",
            reason,
            booking_id
        ))

    flash("Booking cancelled and reason recorded.", "success")
    return redirect(url_for("staff_dashboard"))


# -------------------------
# CUSTOMER DASHBOARD
# -------------------------
@app.route("/dashboard")
def dashboard():
    if not customer_required():
        return redirect(url_for("login"))

    with get_db_connection() as connection:
        counts = connection.execute("""
            SELECT
                SUM(CASE WHEN status = 'Pending' THEN 1 ELSE 0 END) AS pending,
                SUM(CASE WHEN status = 'Approved' THEN 1 ELSE 0 END) AS approved,
                SUM(CASE WHEN status = 'In Progress' THEN 1 ELSE 0 END) AS in_progress,
                SUM(CASE WHEN status = 'Completed' THEN 1 ELSE 0 END) AS completed
            FROM bookings
            WHERE customer_id = ?
        """, (session["customer_id"],)).fetchone()

        recent_bookings = connection.execute("""
            SELECT *
            FROM bookings
            WHERE customer_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 5
        """, (session["customer_id"],)).fetchall()

    return render_template(
        "dashboard.html",
        counts=counts,
        recent_bookings=recent_bookings
    )


# -------------------------
# CUSTOMER BOOKS A SERVICE
# -------------------------
@app.route("/book-service", methods=["GET", "POST"])
def book_service():
    if not customer_required():
        return redirect(url_for("login"))

    if request.method == "POST":
        service_type = request.form.get(
            "service_type", ""
        ).strip()
        service_address = request.form.get(
            "service_address", ""
        ).strip()
        preferred_date = request.form.get(
            "preferred_date", ""
        ).strip()
        preferred_time = request.form.get(
            "preferred_time", ""
        ).strip()
        additional_notes = request.form.get(
            "additional_notes", ""
        ).strip()

        if not all([
            service_type,
            service_address,
            preferred_date,
            preferred_time
        ]):
            flash("Please complete all required fields.", "danger")
            return redirect(url_for("book_service"))

        if service_type not in SERVICES:
            flash(
                "Please choose one of the available services.",
                "danger"
            )
            return redirect(url_for("book_service"))

        try:
            booking_date = date.fromisoformat(preferred_date)
            datetime.strptime(preferred_time, "%H:%M")
        except ValueError:
            flash("Please enter a valid date and time.", "danger")
            return redirect(url_for("book_service"))

        if booking_date < date.today():
            flash("Please choose today or a future date.", "danger")
            return redirect(url_for("book_service"))

        if booking_date.weekday() == 6:
            flash(
                "We are closed on Sundays. Please choose Monday to Saturday.",
                "danger"
            )
            return redirect(url_for("book_service"))

        if not (OPENING_TIME <= preferred_time <= CLOSING_TIME):
            flash(
                "Please choose a start time between 8:00 AM and 5:00 PM.",
                "danger"
            )
            return redirect(url_for("book_service"))

        with get_db_connection() as connection:
            connection.execute("""
                INSERT INTO bookings (
                    customer_id,
                    service_type,
                    service_address,
                    preferred_date,
                    preferred_time,
                    additional_notes,
                    status
                )
                VALUES (?, ?, ?, ?, ?, ?, 'Pending')
            """, (
                session["customer_id"],
                service_type,
                service_address,
                preferred_date,
                preferred_time,
                additional_notes or None
            ))

    # Redirect only after successfully processing a POST.
        flash(
            "Booking request submitted! Staff will contact you to confirm.",
            "success"
        )
        return redirect(url_for("my_bookings"))

    return render_template(
        "book_service.html",
        services=SERVICES,
        today=date.today().isoformat()
    )


# -------------------------
# CUSTOMER CANCELS PENDING BOOKING
# -------------------------
@app.route(
    "/my-bookings/<int:booking_id>/cancel",
    methods=["POST"]
)
def customer_cancel_booking(booking_id):
    if not customer_required():
        return redirect(url_for("login"))

    with get_db_connection() as connection:
        booking = connection.execute("""
            SELECT id, status
            FROM bookings
            WHERE id = ? AND customer_id = ?
        """, (
            booking_id,
            session["customer_id"]
        )).fetchone()

        if not booking:
            flash(
                "Booking not found or you do not have permission to cancel it.",
                "danger"
            )
            return redirect(url_for("my_bookings"))

        if booking["status"] != "Pending":
            flash(
                "Only pending bookings can be cancelled directly. "
                "Please contact staff for assistance with an approved booking.",
                "warning"
            )
            return redirect(url_for("my_bookings"))

        cursor = connection.execute("""
            UPDATE bookings
            SET status = 'Cancelled',
                cancelled_by = ?,
                cancellation_reason = ?,
                cancelled_at = CURRENT_TIMESTAMP
            WHERE id = ?
              AND customer_id = ?
              AND status = 'Pending'
        """, (
            f"Customer ID: {session['customer_id']}",
            "Customer Requested",
            booking_id,
            session["customer_id"]
        ))

        if cursor.rowcount != 1:
            flash(
                "This booking could not be cancelled. Please refresh and try again.",
                "warning"
            )
            return redirect(url_for("my_bookings"))

    flash("Your pending booking has been cancelled.", "success")
    return redirect(url_for("my_bookings"))


# -------------------------
# CUSTOMER VIEW BOOKINGS
# -------------------------
@app.route("/my-bookings")
def my_bookings():
    if not customer_required():
        return redirect(url_for("login"))

    with get_db_connection() as connection:
        bookings = connection.execute("""
            SELECT *
            FROM bookings
            WHERE customer_id = ?
            ORDER BY created_at DESC, id DESC
        """, (session["customer_id"],)).fetchall()

    return render_template(
        "my_bookings.html",
        bookings=bookings
    )


# -------------------------
# LOGOUT
# -------------------------
@app.route("/logout")
def logout():
    session.clear()
    flash("You have logged out.", "info")
    return redirect(url_for("home"))


if __name__ == "__main__":
    app.run(debug=True)
