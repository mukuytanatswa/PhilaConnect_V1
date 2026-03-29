import sqlite3
import json
import os
import hashlib
from datetime import datetime, timedelta

CLINIC_NAME = os.getenv("CLINIC_NAME", "PhilaConnect Clinic")
DASHBOARD_USER = os.getenv("DASHBOARD_USER", "admin")
DASHBOARD_PASS = os.getenv("DASHBOARD_PASS", "admin")

# Database file — absolute path so it resolves correctly regardless of working directory
DB_FILE = os.getenv("DATABASE_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), 'philaconnect.db'))

def _hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Hospitals table
    c.execute('''CREATE TABLE IF NOT EXISTS hospitals (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL
    )''')
    # Doctors table
    c.execute('''CREATE TABLE IF NOT EXISTS doctors (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        specialty TEXT NOT NULL,
        hospital_id INTEGER,
        is_active INTEGER DEFAULT 1,
        available_days TEXT DEFAULT 'Mon,Tue,Wed,Thu,Fri,Sat,Sun'
    )''')
    # Appointments table
    c.execute('''CREATE TABLE IF NOT EXISTS appointments (
        id INTEGER PRIMARY KEY,
        phone TEXT NOT NULL,
        doctor_id INTEGER,
        date TEXT NOT NULL,
        time TEXT NOT NULL,
        status TEXT DEFAULT 'booked',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (doctor_id) REFERENCES doctors(id)
    )''')
    # User states table for persistence
    c.execute('''CREATE TABLE IF NOT EXISTS user_states (
        phone TEXT PRIMARY KEY,
        state TEXT,
        data TEXT
    )''')
    # User profiles table
    c.execute('''CREATE TABLE IF NOT EXISTS user_profiles (
        phone TEXT PRIMARY KEY,
        name TEXT,
        preferred_hospital_id INTEGER,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    # Doctor availability (for future, currently all available)
    c.execute('''CREATE TABLE IF NOT EXISTS doctor_availability (
        id INTEGER PRIMARY KEY,
        doctor_id INTEGER,
        day_of_week INTEGER,  -- 0=Monday, 6=Sunday
        start_time TEXT,
        end_time TEXT,
        FOREIGN KEY (doctor_id) REFERENCES doctors(id)
    )''')
    # Settings table for runtime config (e.g. password override)
    c.execute('''CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )''')
    # Blocked slots — date=NULL means recurring every day
    c.execute('''CREATE TABLE IF NOT EXISTS blocked_slots (
        id INTEGER PRIMARY KEY,
        doctor_id INTEGER,
        date TEXT,
        time TEXT NOT NULL,
        label TEXT DEFAULT 'Unavailable',
        FOREIGN KEY (doctor_id) REFERENCES doctors(id)
    )''')
    # Clinic users — staff accounts tied to a specific hospital
    c.execute('''CREATE TABLE IF NOT EXISTS clinic_users (
        id INTEGER PRIMARY KEY,
        hospital_id INTEGER,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'admin'
    )''')
    # Sessions — tracks logged-in sessions
    c.execute('''CREATE TABLE IF NOT EXISTS sessions (
        token TEXT PRIMARY KEY,
        hospital_id INTEGER,
        role TEXT NOT NULL,
        username TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')

    # Ensure column available_days exists for backward compatibility
    c.execute("PRAGMA table_info(doctors)")
    columns = [row[1] for row in c.fetchall()]
    if 'available_days' not in columns:
        c.execute("ALTER TABLE doctors ADD COLUMN available_days TEXT DEFAULT 'Mon,Tue,Wed,Thu,Fri,Sat,Sun'")
    if 'is_deleted' not in columns:
        c.execute("ALTER TABLE doctors ADD COLUMN is_deleted INTEGER DEFAULT 0")

    # Add reminder_sent column if it doesn't exist (migration for existing databases)
    c.execute("PRAGMA table_info(appointments)")
    appt_columns = [row[1] for row in c.fetchall()]
    if 'reminder_sent' not in appt_columns:
        c.execute("ALTER TABLE appointments ADD COLUMN reminder_sent INTEGER DEFAULT 0")
    if 'no_show_at' not in appt_columns:
        c.execute("ALTER TABLE appointments ADD COLUMN no_show_at TEXT")

    # Backfill any doctors missing available_days
    c.execute("UPDATE doctors SET available_days = 'Mon,Tue,Wed,Thu,Fri' WHERE available_days IS NULL OR available_days = ''")

    # Insert sample data if not exists
    c.execute('SELECT COUNT(*) FROM hospitals')
    if c.fetchone()[0] == 0:
        c.executemany('INSERT INTO hospitals (name) VALUES (?)', [(CLINIC_NAME,)])
        conn.commit()

    # Ensure hospital exists
    c.execute('SELECT id FROM hospitals WHERE name = ?', (CLINIC_NAME,))
    hosp_row = c.fetchone()
    if not hosp_row:
        c.execute('INSERT INTO hospitals (name) VALUES (?)', (CLINIC_NAME,))
        conn.commit()
        hospital_id = c.lastrowid
    else:
        hospital_id = hosp_row[0]

    # Fix any existing doctor rows with hospital_id 0 to the default clinic ID
    c.execute('UPDATE doctors SET hospital_id = ? WHERE hospital_id = 0', (hospital_id,))

    # Update specialties to General Practice
    c.execute('UPDATE doctors SET specialty = "General Practice" WHERE specialty IS NOT NULL')
    conn.commit()

    # Seed default superadmin if clinic_users is empty
    c.execute('SELECT COUNT(*) FROM clinic_users')
    if c.fetchone()[0] == 0:
        # Prefer password already saved in settings table (changed via UI)
        c.execute('SELECT value FROM settings WHERE key = ?', ('dashboard_pass',))
        settings_row = c.fetchone()
        initial_pass = settings_row[0] if settings_row else DASHBOARD_PASS
        c.execute(
            'INSERT INTO clinic_users (hospital_id, username, password_hash, role) VALUES (?, ?, ?, ?)',
            (None, DASHBOARD_USER, _hash_password(initial_pass), 'superadmin')
        )
        conn.commit()

    conn.close()

# ── Auth helpers ─────────────────────────────────────────────────────────────

def get_clinic_user_by_username(username):
    """Returns (id, hospital_id, username, password_hash, role) or None."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, hospital_id, username, password_hash, role FROM clinic_users WHERE username = ?', (username,))
    row = c.fetchone()
    conn.close()
    return row

def verify_password(password, password_hash):
    return _hash_password(password) == password_hash

def create_session(token, hospital_id, role, username):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO sessions (token, hospital_id, role, username) VALUES (?, ?, ?, ?)',
              (token, hospital_id, role, username))
    conn.commit()
    conn.close()

def get_session(token):
    """Returns (hospital_id, role, username) or None."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT hospital_id, role, username FROM sessions WHERE token = ?', (token,))
    row = c.fetchone()
    conn.close()
    return row

def delete_session(token):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM sessions WHERE token = ?', (token,))
    conn.commit()
    conn.close()

def update_clinic_user_password(username, new_password_hash):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE clinic_users SET password_hash = ? WHERE username = ?', (new_password_hash, username))
    conn.commit()
    conn.close()

def list_clinic_users():
    """Returns all clinic users for management."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''SELECT cu.id, cu.username, cu.role, cu.hospital_id, h.name
                 FROM clinic_users cu
                 LEFT JOIN hospitals h ON cu.hospital_id = h.id
                 ORDER BY cu.role, cu.username''')
    rows = c.fetchall()
    conn.close()
    return rows

def create_clinic_user(username, password, role, hospital_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('INSERT INTO clinic_users (hospital_id, username, password_hash, role) VALUES (?, ?, ?, ?)',
              (hospital_id, username, _hash_password(password), role))
    conn.commit()
    conn.close()

def delete_clinic_user(user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM clinic_users WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()

# ── Core bot functions ────────────────────────────────────────────────────────

def set_state(phone, state, data=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    data_json = json.dumps(data) if data else None
    c.execute('INSERT OR REPLACE INTO user_states (phone, state, data) VALUES (?, ?, ?)', (phone, state, data_json))
    conn.commit()
    conn.close()

def get_state(phone):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT state, data FROM user_states WHERE phone = ?', (phone,))
    row = c.fetchone()
    conn.close()
    if row:
        state, data_json = row
        data = json.loads(data_json) if data_json else None
        return state, data
    return None, None

def get_hospitals():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, name FROM hospitals')
    hospitals = c.fetchall()
    conn.close()
    return hospitals

def add_hospital(name):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('INSERT INTO hospitals (name) VALUES (?)', (name,))
    new_id = c.lastrowid
    conn.commit()
    conn.close()
    return new_id

def get_doctors(hospital_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, name, specialty, available_days FROM doctors WHERE hospital_id = ? AND is_active = 1 AND (is_deleted = 0 OR is_deleted IS NULL)', (hospital_id,))
    doctors = c.fetchall()
    conn.close()
    return doctors

def get_available_dates(doctor_id, days_ahead=10):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT available_days FROM doctors WHERE id = ?', (doctor_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return []
    available_days = row[0].split(',') if row[0] else []
    day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    available_indices = [day_names.index(d) for d in available_days if d in day_names]
    dates = []
    today = datetime.now()
    for i in range(1, days_ahead + 1):
        date = today + timedelta(days=i)
        if date.weekday() in available_indices:
            dates.append(date.strftime('%Y-%m-%d'))
    return dates

def get_available_times(doctor_id, date):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "SELECT time FROM appointments WHERE doctor_id=? AND date=? AND status IN ('booked','rescheduled')",
        (doctor_id, date)
    )
    booked = {row[0] for row in c.fetchall()}
    c.execute(
        "SELECT time FROM blocked_slots WHERE doctor_id=? AND (date IS NULL OR date=?)",
        (doctor_id, date)
    )
    blocked = {row[0] for row in c.fetchall()}
    conn.close()
    unavailable = booked | blocked
    times = []
    for hour in range(9, 17):
        for minute in ('00', '30'):
            t = f'{hour:02d}:{minute}'
            if t not in unavailable:
                times.append(t)
    if '17:00' not in unavailable:
        times.append('17:00')
    return times

def book_appointment(phone, doctor_id, date, time):
    print(f"[book_appointment] DB_FILE={DB_FILE}, phone={phone}, doctor_id={doctor_id}, date={date}, time={time}")
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('INSERT INTO appointments (phone, doctor_id, date, time) VALUES (?, ?, ?, ?)', (phone, doctor_id, date, time))
    appointment_id = c.lastrowid
    conn.commit()
    conn.close()
    print(f"[book_appointment] saved appointment_id={appointment_id}")
    return appointment_id

def get_appointments(phone=None, doctor_id=None, include_past=False, hospital_id=None):
    """Get appointments. By default shows only future 'booked' and 'rescheduled' appointments"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    if phone:
        # For patient: show all non-cancelled future booked/rescheduled appointments
        c.execute('''SELECT a.id, d.id, d.name, d.specialty, h.name, a.date, a.time, a.status
                     FROM appointments a
                     JOIN doctors d ON a.doctor_id = d.id
                     JOIN hospitals h ON d.hospital_id = h.id
                     WHERE a.phone = ? AND a.status IN ('booked', 'rescheduled', 'no_show')
                     ORDER BY a.date DESC, a.time DESC''', (phone,))
    elif doctor_id:
        c.execute('''SELECT a.id, a.doctor_id, a.phone, a.date, a.time, a.status
                     FROM appointments a
                     WHERE a.doctor_id = ? AND a.status IN ('booked', 'rescheduled')
                     ORDER BY a.date, a.time''', (doctor_id,))
    else:
        # For dashboard: show all appointments with patient name from user_profiles
        if hospital_id:
            c.execute('''SELECT a.id, a.doctor_id, a.phone,
                                COALESCE(up.name, a.phone) AS patient_name,
                                d.name, h.name, a.date, a.time, a.status, a.reminder_sent
                         FROM appointments a
                         JOIN doctors d ON a.doctor_id = d.id
                         JOIN hospitals h ON d.hospital_id = h.id
                         LEFT JOIN user_profiles up ON a.phone = up.phone
                         WHERE h.id = ?
                         ORDER BY a.date DESC, a.time DESC''', (hospital_id,))
        else:
            c.execute('''SELECT a.id, a.doctor_id, a.phone,
                                COALESCE(up.name, a.phone) AS patient_name,
                                d.name, h.name, a.date, a.time, a.status, a.reminder_sent
                         FROM appointments a
                         JOIN doctors d ON a.doctor_id = d.id
                         JOIN hospitals h ON d.hospital_id = h.id
                         LEFT JOIN user_profiles up ON a.phone = up.phone
                         ORDER BY a.date DESC, a.time DESC''')

    appointments = c.fetchall()
    conn.close()
    return appointments

def cancel_appointment(appointment_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE appointments SET status = "cancelled" WHERE id = ?', (appointment_id,))
    conn.commit()
    conn.close()

def reschedule_appointment(appointment_id, new_date, new_time):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE appointments SET date = ?, time = ?, status = "rescheduled" WHERE id = ?',
              (new_date, new_time, appointment_id))
    conn.commit()
    conn.close()

def mark_no_show(appointment_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE appointments SET status = "no_show", no_show_at = CURRENT_TIMESTAMP WHERE id = ?', (appointment_id,))
    conn.commit()
    conn.close()

def cancel_old_no_shows():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    cutoff = (datetime.now() - timedelta(hours=24)).strftime('%Y-%m-%d %H:%M')
    c.execute("""UPDATE appointments SET status = 'cancelled'
                 WHERE status = 'no_show'
                 AND no_show_at IS NOT NULL
                 AND no_show_at < ?""", (cutoff,))
    conn.commit()
    conn.close()

def mark_appointment_completed(appointment_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE appointments SET status = "completed" WHERE id = ?', (appointment_id,))
    conn.commit()
    conn.close()

def mark_past_appointments_completed():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    c.execute('UPDATE appointments SET status = "completed" WHERE (date || \' \' || time) < ? AND status = "booked"', (now,))
    conn.commit()
    conn.close()

def toggle_doctor(doctor_id, active):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE doctors SET is_active = ? WHERE id = ?', (1 if active else 0, doctor_id))
    conn.commit()
    conn.close()

def update_doctor_availability(doctor_id, available_days):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE doctors SET available_days = ? WHERE id = ?', (available_days, doctor_id))
    conn.commit()
    conn.close()

def get_doctors_all(hospital_id=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if hospital_id:
        c.execute('SELECT id, name, specialty, hospital_id, is_active, available_days FROM doctors WHERE hospital_id = ? AND (is_deleted = 0 OR is_deleted IS NULL)', (hospital_id,))
    else:
        c.execute('SELECT id, name, specialty, hospital_id, is_active, available_days FROM doctors WHERE (is_deleted = 0 OR is_deleted IS NULL)')
    doctors = c.fetchall()
    conn.close()
    return doctors

def get_patients(hospital_id=None):
    """Get patients with visit stats for the dashboard patients tab"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if hospital_id:
        c.execute('''
            SELECT up.phone, up.name, up.created_at,
                   COUNT(a.id) AS visit_count,
                   MAX(a.date) AS last_visit,
                   (SELECT d.name FROM appointments a2
                    JOIN doctors d ON a2.doctor_id = d.id
                    WHERE a2.phone = up.phone AND d.hospital_id = ?
                    ORDER BY a2.date DESC, a2.time DESC LIMIT 1) AS last_doctor
            FROM user_profiles up
            JOIN appointments any_a ON up.phone = any_a.phone
            JOIN doctors any_d ON any_a.doctor_id = any_d.id AND any_d.hospital_id = ?
            LEFT JOIN appointments a ON up.phone = a.phone
                AND a.status = 'completed'
                AND a.doctor_id IN (SELECT id FROM doctors WHERE hospital_id = ?)
            GROUP BY up.phone
            ORDER BY last_visit DESC, up.created_at DESC
        ''', (hospital_id, hospital_id, hospital_id))
    else:
        c.execute('''
            SELECT up.phone, up.name, up.created_at,
                   COUNT(a.id) AS visit_count,
                   MAX(a.date) AS last_visit,
                   (SELECT d.name FROM appointments a2
                    JOIN doctors d ON a2.doctor_id = d.id
                    WHERE a2.phone = up.phone
                    ORDER BY a2.date DESC, a2.time DESC LIMIT 1) AS last_doctor
            FROM user_profiles up
            LEFT JOIN appointments a ON up.phone = a.phone
                AND a.status = 'completed'
            GROUP BY up.phone
            ORDER BY last_visit DESC, up.created_at DESC
        ''')
    patients = c.fetchall()
    conn.close()
    return patients

def get_upcoming_appointments(hours_ahead=48):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    now = datetime.now()
    future = now + timedelta(hours=hours_ahead)
    c.execute('''SELECT a.id, a.phone, d.name, a.date, a.time
                 FROM appointments a
                 JOIN doctors d ON a.doctor_id = d.id
                 WHERE a.status = 'booked'
                   AND a.reminder_sent = 0
                   AND datetime(a.date || " " || a.time) BETWEEN ? AND ?''',
              (now.strftime('%Y-%m-%d %H:%M'), future.strftime('%Y-%m-%d %H:%M')))
    appointments = c.fetchall()
    conn.close()
    return appointments

def mark_reminder_sent(appointment_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE appointments SET reminder_sent = 1 WHERE id = ?', (appointment_id,))
    conn.commit()
    conn.close()

def get_user_profile(phone):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT name, preferred_hospital_id FROM user_profiles WHERE phone = ?', (phone,))
    row = c.fetchone()
    conn.close()
    if row:
        return row[0], row[1]
    return None, None

def set_user_profile(phone, name, preferred_hospital_id=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO user_profiles (phone, name, preferred_hospital_id, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)',
              (phone, name, preferred_hospital_id))
    conn.commit()
    conn.close()

def get_today_count(hospital_id=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    today = datetime.now().strftime('%Y-%m-%d')
    if hospital_id:
        c.execute("""SELECT COUNT(*) FROM appointments a
                     JOIN doctors d ON a.doctor_id = d.id
                     WHERE a.date = ? AND a.status IN ('booked', 'rescheduled')
                     AND d.hospital_id = ?""", (today, hospital_id))
    else:
        c.execute("SELECT COUNT(*) FROM appointments WHERE date = ? AND status IN ('booked', 'rescheduled')", (today,))
    count = c.fetchone()[0]
    conn.close()
    return count

def get_yesterday_count(hospital_id=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    if hospital_id:
        c.execute("""SELECT COUNT(*) FROM appointments a
                     JOIN doctors d ON a.doctor_id = d.id
                     WHERE a.date = ? AND a.status IN ('booked', 'rescheduled', 'completed')
                     AND d.hospital_id = ?""", (yesterday, hospital_id))
    else:
        c.execute("SELECT COUNT(*) FROM appointments WHERE date = ? AND status IN ('booked', 'rescheduled', 'completed')", (yesterday,))
    count = c.fetchone()[0]
    conn.close()
    return count

def get_reminders_sent_today(hospital_id=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    today = datetime.now().strftime('%Y-%m-%d')
    if hospital_id:
        c.execute("""SELECT COUNT(*) FROM appointments a
                     JOIN doctors d ON a.doctor_id = d.id
                     WHERE a.date = ? AND a.reminder_sent = 1
                     AND d.hospital_id = ?""", (today, hospital_id))
    else:
        c.execute("SELECT COUNT(*) FROM appointments WHERE date = ? AND reminder_sent = 1", (today,))
    count = c.fetchone()[0]
    conn.close()
    return count

def get_upcoming_count(hospital_id=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    today = datetime.now().strftime('%Y-%m-%d')
    if hospital_id:
        c.execute("""SELECT COUNT(*) FROM appointments a
                     JOIN doctors d ON a.doctor_id = d.id
                     WHERE a.date >= ? AND a.status IN ('booked', 'rescheduled')
                     AND d.hospital_id = ?""", (today, hospital_id))
    else:
        c.execute("SELECT COUNT(*) FROM appointments WHERE date >= ? AND status IN ('booked', 'rescheduled')", (today,))
    count = c.fetchone()[0]
    conn.close()
    return count

def get_doctor_by_id(doctor_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT name FROM doctors WHERE id=?', (doctor_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 'Your doctor'

def get_setting(key, default=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT value FROM settings WHERE key=?', (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else default

def set_setting(key, value):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)', (key, value))
    conn.commit()
    conn.close()

def add_blocked_slot(doctor_id, time, date=None, label='Unavailable'):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('INSERT INTO blocked_slots (doctor_id, date, time, label) VALUES (?,?,?,?)',
              (doctor_id, date, time, label))
    conn.commit()
    conn.close()

def remove_blocked_slot(slot_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM blocked_slots WHERE id=?', (slot_id,))
    conn.commit()
    conn.close()

def get_blocked_slots(doctor_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, date, time, label FROM blocked_slots WHERE doctor_id=? ORDER BY date IS NOT NULL, date, time',
              (doctor_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def add_blocked_slots_range(doctor_id, start_time, end_time, date=None, label='Unavailable'):
    """Block all 30-min slots from start_time to end_time inclusive."""
    slots = []
    h, m = 9, 0
    while (h, m) <= (17, 0):
        slots.append(f'{h:02d}:{m:02d}')
        m += 30
        if m >= 60:
            m = 0
            h += 1
    try:
        start_idx = slots.index(start_time)
        end_idx = slots.index(end_time)
    except ValueError:
        return
    if end_idx < start_idx:
        return
    for slot in slots[start_idx:end_idx + 1]:
        add_blocked_slot(doctor_id, slot, date, label)

def delete_doctor(doctor_id):
    """Soft-delete a doctor — preserves appointment history."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE doctors SET is_deleted = 1 WHERE id = ?', (doctor_id,))
    conn.commit()
    conn.close()

def delete_hospital(hospital_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM hospitals WHERE id = ?', (hospital_id,))
    conn.commit()
    conn.close()

# Initialize DB on import
init_db()
