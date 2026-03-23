# Appointment Booking & Display Flow Analysis

## Summary
When a patient books an appointment via WhatsApp bot, the appointment may not appear on the dashboard due to several data flow issues. This document traces the complete flow and identifies the root causes.

---

## 1. WHATSAPP BOOKING FLOW

### Step 1: User Selection (logic.py:159-161)
```python
# After user selects hospital → doctor → date → time:
appointment_id = book_appointment(phone, data['doctor_id'], data['date'], data['time'])
set_state(phone, None, {})
send_message(phone, f"APPOINTMENT CONFIRMED\n\nDate: {data['date']}\nTime: {data['time']}\n...")
```

**Data Saved:**
- Phone number (e.g., "+27123456789")
- Doctor ID (integer)
- Date (string: "YYYY-MM-DD")
- Time (string: "HH:MM")
- Status (defaults to 'booked')
- ⚠️ **NO patient name saved at booking time**

### Step 2: Database Insert (db.py:173-177)
```python
def book_appointment(phone, doctor_id, date, time):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('INSERT INTO appointments (phone, doctor_id, date, time) VALUES (?, ?, ?, ?)', 
              (phone, doctor_id, date, time))
    appointment_id = c.lastrowid
    conn.commit()
    conn.close()
    return appointment_id
```

**Schema:**
```sql
appointments (
    id INTEGER PRIMARY KEY,
    phone TEXT NOT NULL,
    doctor_id INTEGER,                    -- Foreign key to doctors table
    date TEXT NOT NULL,
    time TEXT NOT NULL,
    status TEXT DEFAULT 'booked',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (doctor_id) REFERENCES doctors(id)
)
```

---

## 2. DASHBOARD RETRIEVAL FLOW

### Step 1: Endpoint Handler (main.py:36-49)
```python
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    try:
        appointments = get_appointments()  # ← Called with NO parameters
        doctors = get_doctors_all()
        hospitals = get_hospitals()
        ...
        return templates.TemplateResponse("dashboard.html", {
            "request": request, 
            "appointments": appointments,
            ...
        })
```

### Step 2: Database Query (db.py:233-242)
```python
def get_appointments(phone=None, doctor_id=None, include_past=False):
    """Get appointments. By default shows only future 'booked' and 'rescheduled' appointments"""
    
    # FIRST: Auto-mark past appointments as completed
    mark_past_appointments_completed()
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Dashboard call: phone=None, doctor_id=None, include_past=False
    else:  # This branch executes for dashboard
        c.execute('''SELECT a.id, a.doctor_id, a.phone, d.name, h.name, a.date, a.time, a.status
                     FROM appointments a
                     JOIN doctors d ON a.doctor_id = d.id
                     JOIN hospitals h ON d.hospital_id = h.id
                     WHERE a.status IN ('booked', 'rescheduled')
                     ORDER BY a.date, a.time''')
```

**Query Execution Steps:**
1. Call `mark_past_appointments_completed()` - updates old appointments to status='completed'
2. Execute JOIN with doctors table
3. Filter by status IN ('booked', 'rescheduled')
4. Return tuple: (id, doctor_id, phone, doctor_name, hospital_name, date, time, status)

---

## 3. TEMPLATE RENDERING

### HTML Table Render (dashboard.html:1142-1159)
```html
{% for appt in appointments %}
<tr data-appt-id="{{ appt[0] }}" data-doctor-id="{{ appt[1] }}" ...>
    <td><strong>{{ appt[6] }}</strong></td>              <!-- TIME -->
    <td>{{ appt[2] }}</td>                               <!-- ⚠️ PHONE (not name!) -->
    <td>{{ appt[3] }}</td>                               <!-- DOCTOR NAME -->
    <td>General</td>                                     <!-- HARDCODED -->
    <td><span class="status-pill status-confirmed">Confirmed</span></td>  <!-- HARDCODED -->
    <td style="font-size:12px;">Pending ⏳</td>         <!-- HARDCODED -->
    <td><!-- Action buttons --></td>
</tr>
{% endfor %}
```

**Tuple Index Mapping:**
| Index | Data | Source |
|-------|------|--------|
| 0 | Appointment ID | a.id |
| 1 | Doctor ID | a.doctor_id |
| 2 | Patient Contact | a.phone ← **PHONE NUMBER** |
| 3 | Doctor Name | d.name |
| 4 | Hospital Name | h.name |
| 5 | Date | a.date |
| 6 | Time | a.time |
| 7 | Status | a.status |

---

## 🔴 CRITICAL ISSUES FOUND

### Issue #1: Patient Name Display Bug
**Problem:** Template displays `appt[2]` expecting a patient name, but receives a phone number

**Evidence:**
- Dashboard query selects `a.phone` (index 2)
- Template renders it as patient name
- User profile data EXISTS in database but is NOT joined
- Result: Dashboard shows "+27123456789" instead of "John Smith"

**Impact:** Confusing UI, but doesn't prevent display

---

### Issue #2: JOIN Failure When Doctor Doesn't Exist ⚠️ KEY ISSUE
**Problem:** If `doctor_id` in appointments table doesn't match a doctor in the doctors table, the JOIN fails and appointment is excluded from results

**Scenarios Where This Occurs:**
1. **Doctor deleted after booking** - Foreign key constraint not enforced, so appointment stays but doctor is deleted
   ```python
   # Nothing prevents deleting a doctor with existing appointments
   # No CASCADE DELETE configured
   ```

2. **Doctor ID is 0 or NULL** - Invalid foreign key
   ```python
   # If doctor_id not properly set during booking
   # JOIN silently fails, returns 0 results
   ```

3. **Database migration/corruption** - doctor_id points to non-existent ID

**Detection:**
```sql
-- Check for orphaned appointments
SELECT COUNT(*) FROM appointments a
LEFT JOIN doctors d ON a.doctor_id = d.id
WHERE d.id IS NULL;
```

**Current Code Doesn't Handle This:**
```python
# db.py - No error handling, no left join fallback
c.execute('''SELECT ... FROM appointments a
             JOIN doctors d ON a.doctor_id = d.id  ← Fails silently if no match
             ...''')
```

---

### Issue #3: Auto-Completed Appointments Filter
**Problem:** Appointments with date/time in the past are automatically marked as 'completed', then filtered out

**Code (db.py:220-227):**
```python
def mark_past_appointments_completed():
    """Auto-mark appointments as completed if time has passed"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    # Updates any appointment where (date || ' ' || time) < now AND status = 'booked'
    c.execute('UPDATE appointments SET status = "completed" 
              WHERE (date || \' \' || time) < ? AND status = "booked"', (now,))
    conn.commit()
    conn.close()
```

**Issues:**
- Runs EVERY time `get_appointments()` is called
- If system date/time is wrong, future appointments may be marked as past
- No timezone handling

---

### Issue #4: Template Uses Hardcoded Hardcoded Status
**Problem:** Dashboard always shows "Confirmed" status despite actual status in database

**Code (dashboard.html:1153):**
```html
<td><span class="status-pill status-confirmed">Confirmed</span></td>
```

**Should be:**
```html
<td><span class="status-pill status-{{ appt[7]|lower }}">{{ appt[7]|title }}</span></td>
```

---

## 🔍 DIAGNOSTIC CHECKLIST

Run these queries in SQLite to diagnose the issue:

```sql
-- 1. Check if appointments exist with 'booked' status
SELECT COUNT(*) as booked_count 
FROM appointments 
WHERE status = 'booked';

-- 2. Check for appointments with no matching doctor
SELECT a.id, a.phone, a.doctor_id, a.date, a.time 
FROM appointments a
LEFT JOIN doctors d ON a.doctor_id = d.id
WHERE d.id IS NULL;

-- 3. Check doctor_id values are valid
SELECT COUNT(DISTINCT doctor_id) FROM appointments;
SELECT COUNT(*) FROM doctors;

-- 4. Check when last appointment was auto-marked as completed
SELECT COUNT(*) as completed_count 
FROM appointments 
WHERE status = 'completed';

-- 5. List all appointments with their doctor status
SELECT a.id, a.phone, a.doctor_id, d.name, d.is_active, a.date, a.time, a.status
FROM appointments a
LEFT JOIN doctors d ON a.doctor_id = d.id
ORDER BY a.created_at DESC
LIMIT 10;
```

---

## 🔧 ROOT CAUSE ANALYSIS

**Why WhatsApp appointments don't show on dashboard:**

1. **Most Likely:** Doctor was selected during booking but doctor_id doesn't exist in doctors table
   - Causes JOIN to silently exclude the appointment
   - User sees "appointment confirmed" but it's not on dashboard

2. **Secondary:** Wrong doctor_id stored (e.g., 0 or NULL)
   - Signup flow might not properly select doctor
   - JOIN fails, appointment hidden

3. **Tertiary:** Appointment auto-marked as past
   - System date/time incorrect
   - Even fresh appointments show as 'completed'

---

## 📋 RECOMMENDATIONS

1. **Fix JOIN to use LEFT JOIN with NULL checks**
2. **Ensure doctor_id is properly validated before insert**
3. **Add timezone-aware date/time comparison**
4. **Join user_profiles to display actual names**
5. **Use actual status from database instead of hardcoded "Confirmed"**
6. **Add foreign key constraints with CASCADE DELETE** (optional, use with care)
7. **Log appointments that can't be displayed** (debugging)

