from flask import Flask, render_template, request, redirect, session, url_for, jsonify, send_from_directory
from functools import wraps
import sqlite3
from datetime import datetime
import uuid
import os
import time

app = Flask(__name__)
app.secret_key = "parkingapp_secret_2024"

DB_PATH = "database.db"
print("DB location:", os.path.abspath(DB_PATH))


# ================================================================
# DATABASE
# ================================================================

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30.0, check_same_thread=False)
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 30000;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute("PRAGMA journal_mode = WAL;")

    c.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        mobile TEXT UNIQUE
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS slots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        location TEXT,
        vehicle_type TEXT,
        status TEXT,
        price INTEGER
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS bookings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        slot_id INTEGER,
        location TEXT,
        booking_code TEXT UNIQUE,
        valet INTEGER,
        total_price REAL,
        created_at TEXT,
        status TEXT DEFAULT 'confirmed'
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS admins (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT
    )""")

    # Add status column to bookings if it doesn't exist (for existing DBs)
    try:
        c.execute("ALTER TABLE bookings ADD COLUMN status TEXT DEFAULT 'confirmed'")
        conn.commit()
    except Exception:
        pass  # already exists

    # Default admin account
    c.execute("SELECT COUNT(*) FROM admins")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO admins (username, password) VALUES (?, ?)", ("admin", "admin123"))

    conn.commit()
    conn.close()


# ================================================================
# HELPERS
# ================================================================

def get_price(location, vehicle):
    loc = location.lower()
    if "ameerpet" in loc:
        return 50 if vehicle == "car" else 20
    elif "hitech" in loc or "hi-tech" in loc or "hitec" in loc:
        return 80 if vehicle == "car" else 30
    elif "gachibowli" in loc:
        return 100 if vehicle == "car" else 40
    elif "madhapur" in loc:
        return 90 if vehicle == "car" else 35
    elif "begumpet" in loc:
        return 70 if vehicle == "car" else 28
    else:
        return 60 if vehicle == "car" else 25


def run_with_retry(func, max_retries=3, sleep_ms=100):
    last_exc = None
    for i in range(max_retries):
        try:
            return func()
        except sqlite3.OperationalError as e:
            last_exc = e
            if "locked" in str(e).lower():
                time.sleep(sleep_ms / 1000.0)
            else:
                raise
    raise last_exc


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated


# ================================================================
# PWA ROUTES
# ================================================================

@app.route('/manifest.json')
def manifest():
    return send_from_directory('.', 'manifest.json', mimetype='application/manifest+json')


@app.route('/service-worker.js')
def service_worker():
    response = send_from_directory('.', 'service-worker.js', mimetype='application/javascript')
    response.headers['Service-Worker-Allowed'] = '/'
    response.headers['Cache-Control'] = 'no-cache'
    return response


# ================================================================
# USER ROUTES
# ================================================================

@app.route('/')
def home():
    return redirect('/login')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        mobile = request.form.get('mobile', '').strip()

        if not name or not mobile:
            return render_template("login.html", error="Please fill all fields")

        if len(mobile) != 10 or not mobile.isdigit():
            return render_template("login.html", error="Please enter a valid 10-digit mobile number")

        def _save_user():
            conn = get_db()
            c = conn.cursor()
            try:
                c.execute("SELECT id, name FROM users WHERE mobile=?", (mobile,))
                user = c.fetchone()
                if user:
                    user_id = user[0]
                    name_out = user[1]
                else:
                    c.execute("INSERT INTO users (name, mobile) VALUES (?,?)", (name, mobile))
                    user_id = c.lastrowid
                    conn.commit()
                    name_out = name
                return user_id, name_out
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

        try:
            user_id, saved_name = run_with_retry(_save_user)
        except Exception as e:
            return f"Login error: {e}", 500

        session['user_id'] = user_id
        session['name'] = saved_name
        session['mobile'] = mobile
        return redirect(url_for('dashboard'))

    return render_template("login.html")


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("SELECT * FROM bookings WHERE user_id=? ORDER BY id DESC", (session['user_id'],))
        bookings = c.fetchall()
    except Exception:
        bookings = []
    finally:
        conn.close()

    return render_template("dashboard.html", name=session['name'], bookings=bookings)


@app.route('/vehicle', methods=['GET', 'POST'])
def vehicle():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        vehicle_type = request.form.get('vehicle')
        if vehicle_type not in ('car', 'bike'):
            return render_template("vehicle.html", error="Invalid vehicle type")
        return redirect(url_for('location', vehicle=vehicle_type))

    return render_template("vehicle.html")


@app.route('/location', methods=['GET', 'POST'])
def location():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    vehicle_type = request.args.get('vehicle')
    if vehicle_type not in ('car', 'bike'):
        return redirect(url_for('vehicle'))

    if request.method == 'POST':
        loc = request.form.get('location', '').strip()
        if not loc:
            return render_template("location.html", vehicle=vehicle_type, error="Please enter a location")
        return redirect(url_for('parking', vehicle=vehicle_type, location=loc))

    return render_template("location.html", vehicle=vehicle_type)


@app.route('/parking')
def parking():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    vehicle_type = request.args.get('vehicle')
    loc = request.args.get('location', '').strip()

    if vehicle_type not in ('car', 'bike') or not loc:
        return "Missing or invalid vehicle/location", 400

    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("SELECT COUNT(*) FROM slots WHERE location=?", (loc,))
        count = c.fetchone()[0]

        if count == 0:
            price_car = get_price(loc, "car")
            price_bike = get_price(loc, "bike")
            for _ in range(5):
                c.execute("INSERT INTO slots (location, vehicle_type, status, price) VALUES (?,?,?,?)",
                          (loc, "car", "available", price_car))
            for _ in range(5):
                c.execute("INSERT INTO slots (location, vehicle_type, status, price) VALUES (?,?,?,?)",
                          (loc, "bike", "available", price_bike))
            conn.commit()

        c.execute("SELECT * FROM slots WHERE vehicle_type=? AND location=? AND status='available'",
                  (vehicle_type, loc))
        slots = c.fetchall()
    except Exception as e:
        conn.rollback()
        return f"Error loading slots: {e}", 500
    finally:
        conn.close()

    return render_template("parking.html", slots=slots, location=loc, vehicle_type=vehicle_type)


@app.route('/book/<int:slot_id>')
def book(slot_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("SELECT id, location, vehicle_type, status, price FROM slots WHERE id=?", (slot_id,))
        slot = c.fetchone()
    except Exception:
        slot = None
    finally:
        conn.close()

    if not slot:
        return "Slot not found", 404
    if slot[3] != "available":
        return "This slot is no longer available. Please choose another.", 409

    return render_template("booking.html", price=slot[4], slot_id=slot[0],
                           location=slot[1], vehicle_type=slot[2])


@app.route('/calculate', methods=['POST'])
def calculate():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    try:
        slot_id   = int(request.form.get('slot_id'))
        entry     = request.form.get('entry')
        exit_time = request.form.get('exit')
        valet     = request.form.get('valet', 'no')

        if not entry or not exit_time:
            return "Please select entry and exit time", 400

        entry_dt = datetime.strptime(entry, "%Y-%m-%dT%H:%M")
        exit_dt  = datetime.strptime(exit_time, "%Y-%m-%dT%H:%M")

        now = datetime.now().replace(second=0, microsecond=0)
        if entry_dt < now:
            return "Entry time cannot be in the past", 400

        diff_seconds = (exit_dt - entry_dt).total_seconds()
        if diff_seconds <= 0:
            return "Exit time must be after entry time", 400

        hours = max(diff_seconds / 3600.0, 1.0)

        conn = get_db()
        c = conn.cursor()
        try:
            c.execute("SELECT price, location, status FROM slots WHERE id=?", (slot_id,))
            data = c.fetchone()
        except Exception:
            data = None
        finally:
            conn.close()

        if not data:
            return "Slot not found", 404
        if data[2] != "available":
            return "This slot is no longer available", 409

        price_per_hour = data[0]
        location       = data[1]
        total = hours * price_per_hour
        if valet == "yes":
            total += 30

        total = round(total, 2)
        hours = round(hours, 2)

        session['total_price']  = total
        session['slot_id']      = slot_id
        session['valet']        = valet
        session['location']     = location
        session['hours']        = hours
        session['payment_done'] = False

        return render_template("payment.html", total=total, slot_id=slot_id,
                               location=location, valet=valet, hours=hours)

    except ValueError as e:
        return f"Invalid input: {e}", 400
    except Exception as e:
        return f"Error in calculation: {e}", 500


@app.route('/payment', methods=['POST'])
def payment():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    try:
        slot_id   = int(request.form.get('slot_id'))
        entry     = request.form.get('entry')
        exit_time = request.form.get('exit')
        valet     = request.form.get('valet', 'no')

        if not entry or not exit_time:
            return "Please select entry and exit time", 400

        try:
            entry_dt = datetime.strptime(entry, "%Y-%m-%dT%H:%M")
            exit_dt  = datetime.strptime(exit_time, "%Y-%m-%dT%H:%M")
        except ValueError:
            return "Invalid date format", 400

        now = datetime.now().replace(second=0, microsecond=0)
        if entry_dt < now:
            return "Entry time cannot be in the past", 400

        diff_seconds = (exit_dt - entry_dt).total_seconds()
        if diff_seconds <= 0:
            return "Exit time must be after entry time", 400

        hours = max(diff_seconds / 3600.0, 1.0)

        conn = get_db()
        c = conn.cursor()
        try:
            c.execute("SELECT price, location, status FROM slots WHERE id=?", (slot_id,))
            data = c.fetchone()
        except Exception:
            data = None
        finally:
            conn.close()

        if not data:
            return "Slot not found", 404
        if data[2] != "available":
            return "This slot is no longer available", 409

        price_per_hour = data[0]
        location       = data[1]
        total = hours * price_per_hour
        if valet == "yes":
            total += 30

        total = round(total, 2)
        hours = round(hours, 2)

        session['total_price']  = total
        session['slot_id']      = slot_id
        session['valet']        = valet
        session['location']     = location
        session['hours']        = hours
        session['payment_done'] = False

        return render_template("payment.html", total=total, slot_id=slot_id,
                               location=location, valet=valet, hours=hours)

    except ValueError as e:
        return f"Invalid input: {e}", 400
    except Exception as e:
        return f"Payment error: {e}", 500


@app.route('/processing')
def processing():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if not session.get('slot_id') or session.get('payment_done'):
        return redirect(url_for('vehicle'))

    session['payment_done'] = True

    return render_template("processing.html",
                           slot_id=session.get('slot_id'),
                           valet=session.get('valet', 'no'),
                           total=session.get('total_price', 0))


@app.route('/confirm')
def confirm():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if not session.get('payment_done'):
        return redirect(url_for('vehicle'))

    total    = session.get('total_price')
    location = session.get('location')
    slot_id  = session.get('slot_id')
    valet    = session.get('valet', 'no')

    if total is None or not location or not slot_id:
        return "Missing booking data. Please start over.", 400

    def _confirm_booking():
        conn = get_db()
        c = conn.cursor()
        try:
            c.execute("SELECT status FROM slots WHERE id=?", (slot_id,))
            slot = c.fetchone()

            if not slot:
                raise ValueError("Slot not found")
            if slot[0] != "available":
                raise ValueError("Sorry, this slot was just taken. Please choose another.")

            c.execute("UPDATE slots SET status='booked' WHERE id=?", (slot_id,))

            booking_code = "PW" + str(uuid.uuid4())[:8].upper()
            created_at   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            c.execute("""INSERT INTO bookings
                (user_id, slot_id, location, booking_code, valet, total_price, created_at, status)
                VALUES (?,?,?,?,?,?,?,?)""",
                (session['user_id'], slot_id, location, booking_code,
                 1 if valet == "yes" else 0, total, created_at, 'confirmed'))

            conn.commit()
            return booking_code
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    try:
        booking_code = run_with_retry(_confirm_booking)
    except ValueError as e:
        return str(e), 409
    except Exception as e:
        if "locked" in str(e).lower():
            return "The slot is temporarily busy. Please try again in a moment.", 500
        return f"Booking failed: {e}", 500

    for key in ('total_price', 'slot_id', 'valet', 'location', 'hours', 'payment_done'):
        session.pop(key, None)

    return render_template("success.html", booking_code=booking_code, total=total, location=location)


@app.route('/confirm_payment', methods=['GET', 'POST'])
def confirm_payment():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if not session.get('slot_id'):
        return redirect(url_for('vehicle'))
    session['payment_done'] = True
    session.modified = True
    return redirect(url_for('confirm'))


# ================================================================
# ADMIN ROUTES
# ================================================================

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if session.get('admin_logged_in'):
        return redirect(url_for('admin_dashboard'))

    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT id FROM admins WHERE username=? AND password=?", (username, password))
        admin = c.fetchone()
        conn.close()

        if admin:
            session['admin_logged_in'] = True
            session['admin_username'] = username
            return redirect(url_for('admin_dashboard'))
        else:
            error = "Invalid credentials"

    return render_template("admin_login.html", error=error)


@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    session.pop('admin_username', None)
    return redirect(url_for('admin_login'))


@app.route('/admin')
@admin_required
def admin_dashboard():
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM bookings")
    total_bookings = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]

    c.execute("SELECT COALESCE(SUM(total_price), 0) FROM bookings")
    total_revenue = round(c.fetchone()[0], 2)

    c.execute("SELECT COUNT(*) FROM slots WHERE status='available'")
    available_slots = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM slots WHERE status='booked'")
    booked_slots = c.fetchone()[0]

    c.execute("""
        SELECT b.id, u.name, u.mobile, b.location, b.booking_code,
               b.valet, b.total_price, b.created_at, b.slot_id,
               COALESCE(b.status, 'confirmed') as status
        FROM bookings b
        JOIN users u ON b.user_id = u.id
        ORDER BY b.id DESC LIMIT 5
    """)
    recent_bookings = c.fetchall()

    c.execute("""
        SELECT location, COUNT(*) as count, COALESCE(SUM(total_price), 0) as revenue
        FROM bookings GROUP BY location ORDER BY revenue DESC
    """)
    location_stats = c.fetchall()

    conn.close()

    return render_template("admin_dashboard.html",
                           total_bookings=total_bookings,
                           total_users=total_users,
                           total_revenue=total_revenue,
                           available_slots=available_slots,
                           booked_slots=booked_slots,
                           recent_bookings=recent_bookings,
                           location_stats=location_stats,
                           admin_username=session.get('admin_username'))


@app.route('/admin/bookings')
@admin_required
def admin_bookings():
    search = request.args.get('search', '').strip()
    status_filter = request.args.get('status', '').strip()

    conn = get_db()
    c = conn.cursor()

    query = """
        SELECT b.id, u.name, u.mobile, b.location, b.booking_code,
               b.valet, b.total_price, b.created_at, b.slot_id,
               COALESCE(b.status, 'confirmed') as status
        FROM bookings b
        JOIN users u ON b.user_id = u.id
        WHERE 1=1
    """
    params = []

    if search:
        query += " AND (u.name LIKE ? OR u.mobile LIKE ? OR b.booking_code LIKE ? OR b.location LIKE ?)"
        params += [f"%{search}%"] * 4

    if status_filter:
        query += " AND COALESCE(b.status, 'confirmed') = ?"
        params.append(status_filter)

    query += " ORDER BY b.id DESC"

    c.execute(query, params)
    bookings = c.fetchall()
    conn.close()

    return render_template("admin_bookings.html", bookings=bookings, search=search, status_filter=status_filter)


@app.route('/admin/bookings/<int:booking_id>/approve', methods=['POST'])
@admin_required
def admin_approve_booking(booking_id):
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("UPDATE bookings SET status='confirmed' WHERE id=?", (booking_id,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        return f"Error: {e}", 500
    finally:
        conn.close()
    return redirect(url_for('admin_bookings'))


@app.route('/admin/bookings/<int:booking_id>/cancel', methods=['POST'])
@admin_required
def admin_cancel_booking(booking_id):
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("SELECT slot_id FROM bookings WHERE id=?", (booking_id,))
        row = c.fetchone()
        if row:
            c.execute("UPDATE slots SET status='available' WHERE id=?", (row[0],))
        c.execute("UPDATE bookings SET status='cancelled' WHERE id=?", (booking_id,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        return f"Error: {e}", 500
    finally:
        conn.close()
    return redirect(url_for('admin_bookings'))


@app.route('/admin/users')
@admin_required
def admin_users():
    search = request.args.get('search', '').strip()
    conn = get_db()
    c = conn.cursor()

    if search:
        c.execute("""
            SELECT u.id, u.name, u.mobile,
                   COUNT(b.id) as booking_count,
                   COALESCE(SUM(b.total_price), 0) as total_spent
            FROM users u
            LEFT JOIN bookings b ON u.id = b.user_id
            WHERE u.name LIKE ? OR u.mobile LIKE ?
            GROUP BY u.id ORDER BY booking_count DESC
        """, (f"%{search}%", f"%{search}%"))
    else:
        c.execute("""
            SELECT u.id, u.name, u.mobile,
                   COUNT(b.id) as booking_count,
                   COALESCE(SUM(b.total_price), 0) as total_spent
            FROM users u
            LEFT JOIN bookings b ON u.id = b.user_id
            GROUP BY u.id ORDER BY booking_count DESC
        """)

    users = c.fetchall()
    conn.close()
    return render_template("admin_users.html", users=users, search=search)


@app.route('/admin/slots')
@admin_required
def admin_slots():
    location_filter = request.args.get('location', '').strip()
    conn = get_db()
    c = conn.cursor()

    if location_filter:
        c.execute("SELECT * FROM slots WHERE location LIKE ? ORDER BY location, vehicle_type",
                  (f"%{location_filter}%",))
    else:
        c.execute("SELECT * FROM slots ORDER BY location, vehicle_type")

    slots = c.fetchall()

    c.execute("SELECT DISTINCT location FROM slots ORDER BY location")
    locations = [row[0] for row in c.fetchall()]
    conn.close()

    return render_template("admin_slots.html", slots=slots, locations=locations, location_filter=location_filter)


@app.route('/admin/slots/add', methods=['POST'])
@admin_required
def admin_add_slot():
    location = request.form.get('location', '').strip()
    vehicle_type = request.form.get('vehicle_type', '').strip()
    price = request.form.get('price', '').strip()
    count = int(request.form.get('count', 1))

    if not location or vehicle_type not in ('car', 'bike') or not price:
        return "Invalid data", 400

    conn = get_db()
    c = conn.cursor()
    try:
        for _ in range(count):
            c.execute("INSERT INTO slots (location, vehicle_type, status, price) VALUES (?,?,?,?)",
                      (location, vehicle_type, 'available', int(price)))
        conn.commit()
    except Exception as e:
        conn.rollback()
        return f"Error: {e}", 500
    finally:
        conn.close()

    return redirect(url_for('admin_slots'))


@app.route('/admin/slots/<int:slot_id>/edit', methods=['POST'])
@admin_required
def admin_edit_slot(slot_id):
    price = request.form.get('price', '').strip()
    status = request.form.get('status', '').strip()

    if not price or status not in ('available', 'booked', 'maintenance'):
        return "Invalid data", 400

    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("UPDATE slots SET price=?, status=? WHERE id=?", (int(price), status, slot_id))
        conn.commit()
    except Exception as e:
        conn.rollback()
        return f"Error: {e}", 500
    finally:
        conn.close()

    return redirect(url_for('admin_slots'))


@app.route('/admin/slots/<int:slot_id>/delete', methods=['POST'])
@admin_required
def admin_delete_slot(slot_id):
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("DELETE FROM slots WHERE id=? AND status='available'", (slot_id,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        return f"Error: {e}", 500
    finally:
        conn.close()

    return redirect(url_for('admin_slots'))


@app.route('/admin/analytics')
@admin_required
def admin_analytics():
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT DATE(created_at) as day, COUNT(*) as bookings, COALESCE(SUM(total_price), 0) as revenue
        FROM bookings
        WHERE created_at >= DATE('now', '-7 days')
        GROUP BY day ORDER BY day ASC
    """)
    daily_stats = c.fetchall()

    c.execute("""
        SELECT location, COUNT(*) as bookings, COALESCE(SUM(total_price), 0) as revenue
        FROM bookings GROUP BY location ORDER BY revenue DESC
    """)
    location_stats = c.fetchall()

    c.execute("SELECT COUNT(*) FROM bookings WHERE valet=1")
    valet_count = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM bookings WHERE valet=0")
    normal_count = c.fetchone()[0]

    c.execute("""
        SELECT u.name, u.mobile, COUNT(b.id) as bookings, COALESCE(SUM(b.total_price), 0) as spent
        FROM users u JOIN bookings b ON u.id = b.user_id
        GROUP BY u.id ORDER BY spent DESC LIMIT 5
    """)
    top_users = c.fetchall()

    conn.close()

    return render_template("admin_analytics.html",
                           daily_stats=daily_stats,
                           location_stats=location_stats,
                           valet_count=valet_count,
                           normal_count=normal_count,
                           top_users=top_users)


# ================================================================
# MAIN
# ================================================================

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True, threaded=True, use_reloader=False)
