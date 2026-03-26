import sqlite3
import json
from datetime import datetime, timedelta

# Database file
DB_FILE = 'philaconnect.db'

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

    # Ensure column available_days exists for backward compatibility
    c.execute("PRAGMA table_info(doctors)")
    columns = [row[1] for row in c.fetchall()]
    if 'available_days' not in columns:
        c.execute("ALTER TABLE doctors ADD COLUMN available_days TEXT DEFAULT 'Mon,Tue,Wed,Thu,Fri,Sat,Sun'")

    # Backfill any doctors missing available_days
    c.execute("UPDATE doctors SET available_days = 'Mon,Tue,Wed,Thu,Fri' WHERE available_days IS NULL OR available_days = ''")

    # Insert sample data if not exists
    c.execute('SELECT COUNT(*) FROM hospitals')
    if c.fetchone()[0] == 0:
        hospitals = [
            ('The Riverside Cottage',),
        ]
        c.executemany('INSERT INTO hospitals (name) VALUES (?)', hospitals)
        conn.commit()

    # Ensure hospital exists
    c.execute('SELECT id FROM hospitals WHERE name = "The Riverside Cottage"')
    hosp_row = c.fetchone()
    if not hosp_row:
        c.execute('INSERT INTO hospitals (name) VALUES (?)', ('The Riverside Cottage',))
        conn.commit()
        hospital_id = c.lastrowid
    else:
        hospital_id = hosp_row[0]

    # Insert doctors if they don't exist
    c.execute('SELECT COUNT(*) FROM doctors')
    if c.fetchone()[0] == 0:
        doctors = [
            ('Dr. Kotzé-Scott', 'General Practice', hospital_id, 'Mon,Tue,Wed,Thu,Fri,Sat,Sun'),
            ('Dr. Awe', 'General Practice', hospital_id, 'Mon,Tue,Wed,Thu,Fri,Sat,Sun'),
            ('Dr. Blumenthal', 'General Practice', hospital_id, 'Mon,Tue,Wed,Thu,Fri,Sat,Sun')
        ]
        c.executemany('INSERT INTO doctors (name, specialty, hospital_id, available_days) VALUES (?, ?, ?, ?)', doctors)
        conn.commit()

    # Fix any existing doctor rows with hospital_id 0 to the default clinic ID
    c.execute('UPDATE doctors SET hospital_id = ? WHERE hospital_id = 0', (hospital_id,))

    # Update specialties to General Practice
    c.execute('UPDATE doctors SET specialty = "General Practice" WHERE specialty IS NOT NULL')
    conn.commit()
    conn.close()

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

def get_doctors(hospital_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, name, specialty, available_days FROM doctors WHERE hospital_id = ? AND is_active = 1', (hospital_id,))
    doctors = c.fetchall()
    conn.close()
    return doctors

def get_available_dates(doctor_id, days_ahead=14):
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
    # For now, 9am to 5pm every hour
    times = []
    for hour in range(9, 18):
        times.append(f'{hour:02d}:00')
    return times

def book_appointment(phone, doctor_id, date, time):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('INSERT INTO appointments (phone, doctor_id, date, time) VALUES (?, ?, ?, ?)', (phone, doctor_id, date, time))
    appointment_id = c.lastrowid
    conn.commit()
    conn.close()
    return appointment_id

def get_appointments(phone=None, doctor_id=None, include_past=False):
    """Get appointments. By default shows only future 'booked' and 'rescheduled' appointments"""
    # Don't auto-mark past appointments as completed - let user's actions determine status
    # mark_past_appointments_completed()
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    if phone:
        # For patient: show all non-cancelled future booked/rescheduled appointments
        c.execute('''SELECT a.id, d.id, d.name, d.specialty, h.name, a.date, a.time, a.status
                     FROM appointments a
                     JOIN doctors d ON a.doctor_id = d.id
                     JOIN hospitals h ON d.hospital_id = h.id
                     WHERE a.phone = ? AND a.status IN ('booked', 'rescheduled')
                     ORDER BY a.date DESC, a.time DESC''', (phone,))
    elif doctor_id:
        c.execute('''SELECT a.id, a.doctor_id, a.phone, a.date, a.time, a.status
                     FROM appointments a
                     WHERE a.doctor_id = ? AND a.status IN ('booked', 'rescheduled')
                     ORDER BY a.date, a.time''', (doctor_id,))
    else:
        # For dashboard: show all appointments with patient name from user_profiles
        c.execute('''SELECT a.id, a.doctor_id, a.phone,
                            COALESCE(up.name, a.phone) AS patient_name,
                            d.name, h.name, a.date, a.time, a.status
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

def mark_appointment_completed(appointment_id):
    """Mark an appointment as completed"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE appointments SET status = "completed" WHERE id = ?', (appointment_id,))
    conn.commit()
    conn.close()

def mark_past_appointments_completed():
    """Auto-mark appointments as completed if time has passed"""
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

def get_doctors_all():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, name, specialty, hospital_id, is_active, available_days FROM doctors')
    doctors = c.fetchall()
    conn.close()
    return doctors

def get_upcoming_appointments(hours_ahead=48):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    now = datetime.now()
    future = now + timedelta(hours=hours_ahead)
    c.execute('''SELECT a.id, a.phone, d.name, a.date, a.time
                 FROM appointments a
                 JOIN doctors d ON a.doctor_id = d.id
                 WHERE a.status = 'booked' AND datetime(a.date || " " || a.time) BETWEEN ? AND ?''',
              (now.strftime('%Y-%m-%d %H:%M'), future.strftime('%Y-%m-%d %H:%M')))
    appointments = c.fetchall()
    conn.close()
    return appointments

def get_user_profile(phone):
    """Get user profile by phone number, returns (name, preferred_hospital_id) or (None, None)"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT name, preferred_hospital_id FROM user_profiles WHERE phone = ?', (phone,))
    row = c.fetchone()
    conn.close()
    if row:
        return row[0], row[1]
    return None, None

def set_user_profile(phone, name, preferred_hospital_id=None):
    """Set or update user profile"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO user_profiles (phone, name, preferred_hospital_id, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)', 
              (phone, name, preferred_hospital_id))
    conn.commit()
    conn.close()

# Initialize DB on import
init_db()
