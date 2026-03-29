from fastapi import FastAPI, Request, Query, Form
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from logic import handle_message
from db import (
    get_appointments, toggle_doctor, get_doctors_all, get_hospitals,
    book_appointment, update_doctor_availability, cancel_appointment,
    reschedule_appointment, get_user_profile, set_user_profile,
    mark_appointment_completed, mark_no_show, cancel_old_no_shows,
    get_upcoming_appointments, mark_reminder_sent,
    get_today_count, get_yesterday_count, get_reminders_sent_today, get_upcoming_count,
    get_patients, get_available_times, add_blocked_slot, remove_blocked_slot,
    get_blocked_slots, get_setting, set_setting, DB_FILE,
    get_clinic_user_by_username, verify_password, create_session,
    get_session, delete_session, update_clinic_user_password, _hash_password,
    list_clinic_users, create_clinic_user, delete_clinic_user, add_hospital,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from starlette.middleware.base import BaseHTTPMiddleware
from whatsapp import send_message
import asyncio
import hashlib
import secrets
import sqlite3
import json
import os
import csv
import io
import hmac

app = FastAPI()

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        public = ("/login", "/webhook")
        if any(request.url.path.startswith(p) for p in public):
            return await call_next(request)
        token = request.cookies.get("session")
        if not token:
            return RedirectResponse("/login")
        session = get_session(token)
        if not session:
            return RedirectResponse("/login")
        hospital_id, role, username = session
        request.state.hospital_id = hospital_id  # None means superadmin (all clinics)
        request.state.role = role
        request.state.username = username
        return await call_next(request)

app.add_middleware(AuthMiddleware)

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "philaconnect_verify")
CLINIC_NAME = os.getenv("CLINIC_NAME", "PhilaConnect Clinic")
TIER = os.getenv("TIER", "solo")
TIER_LIMITS = {"solo": 1, "practice": 5, "enterprise": None}
WHATSAPP_APP_SECRET = os.getenv("WHATSAPP_APP_SECRET", "")

_missing_vars = [v for v in ["WHATSAPP_TOKEN", "WHATSAPP_PHONE_ID", "WHATSAPP_APP_SECRET"] if not os.getenv(v)]
if _missing_vars:
    print(f"WARNING: Missing env vars: {', '.join(_missing_vars)} — WhatsApp messaging will not work.", flush=True)

def _get_filter_hospital_id(request: Request):
    """Returns hospital_id to filter by, or None for superadmin (see all)."""
    role = getattr(request.state, 'role', None)
    if role == 'superadmin':
        return None
    return getattr(request.state, 'hospital_id', None)

def _get_clinic_name(hospital_id):
    """Get clinic name for a given hospital_id, or 'All Clinics' if None."""
    if hospital_id is None:
        return "All Clinics"
    hospitals = get_hospitals()
    match = next((h[1] for h in hospitals if h[0] == hospital_id), None)
    return match or CLINIC_NAME

# Templates
templates = Jinja2Templates(directory="templates")

# Meta webhook verification
@app.get("/webhook")
def verify(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    if hub_mode == "subscribe" and hub_token == VERIFY_TOKEN:
        return int(hub_challenge)
    return "Verification failed"

# Endpoint for receiving messages from WhatsApp
@app.post("/webhook")
async def webhook(request: Request):
    body = await request.body()
    if WHATSAPP_APP_SECRET:
        sig_header = request.headers.get("X-Hub-Signature-256", "")
        expected = "sha256=" + hmac.new(WHATSAPP_APP_SECRET.encode(), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig_header, expected):
            return JSONResponse({"status": "unauthorized"}, status_code=401)
    data = json.loads(body)
    handle_message(data)
    return {"status": "ok"}

# Login / Logout
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {})

@app.post("/login")
async def login(username: str = Form(...), password: str = Form(...)):
    user = get_clinic_user_by_username(username)
    if user and verify_password(password, user[3]):
        # user: (id, hospital_id, username, password_hash, role)
        token = secrets.token_hex(32)
        create_session(token, user[1], user[4], user[2])
        resp = RedirectResponse(url="/dashboard", status_code=303)
        resp.set_cookie("session", token, httponly=True, samesite="lax")
        return resp
    return RedirectResponse(url="/login?error=1", status_code=303)

@app.get("/logout")
async def logout(request: Request):
    token = request.cookies.get("session")
    if token:
        delete_session(token)
    resp = RedirectResponse(url="/login", status_code=303)
    resp.delete_cookie("session")
    return resp

# Dashboard
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    try:
        filter_hid = _get_filter_hospital_id(request)
        appointments = get_appointments(hospital_id=filter_hid)
        doctors = get_doctors_all(hospital_id=filter_hid)
        hospitals = get_hospitals()
        clinic_name = _get_clinic_name(filter_hid)
        # Per-clinic stats for superadmin home view
        clinic_stats = {}
        if getattr(request.state, 'role', None) == 'superadmin':
            for h in hospitals:
                h_id = h[0]
                h_docs = get_doctors_all(hospital_id=h_id)
                clinic_stats[h_id] = {
                    'today': get_today_count(hospital_id=h_id),
                    'doctors': len(h_docs),
                    'active_doctors': sum(1 for d in h_docs if d[4] == 1),
                    'upcoming': get_upcoming_count(hospital_id=h_id),
                }
        active_doctors = sum(1 for doc in doctors if doc[4] == 1)
        appt_counts = {}
        for appt in appointments:
            doc_id = appt[1]
            appt_counts[doc_id] = appt_counts.get(doc_id, 0) + 1
        today_count = get_today_count(hospital_id=filter_hid)
        yesterday_count = get_yesterday_count(hospital_id=filter_hid)
        reminders_sent_today = get_reminders_sent_today(hospital_id=filter_hid)
        upcoming_count = get_upcoming_count(hospital_id=filter_hid)
        booked_count = sum(1 for a in appointments if a[8] == 'booked')
        rescheduled_count = sum(1 for a in appointments if a[8] == 'rescheduled')
        cancelled_count = sum(1 for a in appointments if a[8] == 'cancelled')
        no_show_count = sum(1 for a in appointments if a[8] == 'no_show')
        patients = get_patients(hospital_id=filter_hid)
        return templates.TemplateResponse(request, "dashboard.html", {
            "appointments": appointments,
            "doctors": doctors,
            "hospitals": hospitals,
            "clinic_name": clinic_name,
            "active_doctors": active_doctors,
            "appt_counts": appt_counts,
            "today_count": today_count,
            "yesterday_count": yesterday_count,
            "reminders_sent_today": reminders_sent_today,
            "upcoming_count": upcoming_count,
            "booked_count": booked_count,
            "rescheduled_count": rescheduled_count,
            "cancelled_count": cancelled_count,
            "no_show_count": no_show_count,
            "patients": patients,
            "patients_count": len(patients),
            "current_role": getattr(request.state, 'role', 'admin'),
            "current_username": getattr(request.state, 'username', ''),
            "clinic_stats": clinic_stats,
        })
    except Exception as e:
        print(f"Error loading dashboard: {e}")
        import traceback
        with open('error.log', 'w') as f:
            f.write(f"Error: {e}\n")
            traceback.print_exc(file=f)
        traceback.print_exc()
        return HTMLResponse("<h1>Internal Server Error</h1><p>Please try again later.</p>", status_code=500)

@app.post("/toggle_doctor")
async def toggle_doc(doctor_id: int = Form(...), active: bool = Form(...)):
    toggle_doctor(doctor_id, active)
    return {"status": "ok"}

@app.post("/update_doctor_availability")
async def update_availability(doctor_id: int = Form(...), available_days: str = Form(...)):
    update_doctor_availability(doctor_id, available_days)
    return {"status": "ok"}

@app.post("/add_appointment")
async def add_appt(
    request: Request,
    patient_name: str = Form(...),
    phone: str = Form(...),
    date: str = Form(...),
    time: str = Form(...),
    doctor_id: int = Form(...),
    type: str = Form("General Consultation"),
    notes: str = Form("")
):
    patient_name = patient_name.strip().title()
    appointment_id = book_appointment(phone, doctor_id, date, time)
    set_user_profile(phone, patient_name)
    doctors = get_doctors_all()
    doctor_name = next((d[1] for d in doctors if d[0] == doctor_id), "Doctor")
    clinic_name = _get_clinic_name(_get_filter_hospital_id(request))
    send_message(phone, f"Hello {patient_name}, your appointment at {clinic_name} is confirmed for {date} at {time} with {doctor_name}.")
    return RedirectResponse(url="/dashboard", status_code=303)

@app.post("/add_doctor")
async def add_doc(
    request: Request,
    first_name: str = Form(...),
    surname: str = Form(...),
    specialty: str = Form("General Practice")
):
    limit = TIER_LIMITS.get(TIER)
    filter_hid = _get_filter_hospital_id(request)
    if limit is not None and len(get_doctors_all(hospital_id=filter_hid)) >= limit:
        return RedirectResponse(url="/dashboard?error=doctor_limit", status_code=303)
    name = f"Dr. {first_name.strip().title()} {surname.strip().title()}"
    # Use the logged-in user's hospital; fall back to first hospital for superadmin
    hospital_id = filter_hid if filter_hid else get_hospitals()[0][0]
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('INSERT INTO doctors (name, specialty, hospital_id, available_days) VALUES (?, ?, ?, ?)',
              (name, specialty, hospital_id, 'Mon,Tue,Wed,Thu,Fri'))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/dashboard", status_code=303)

@app.post("/cancel_appointment")
async def cancel_appt(appointment_id: int = Form(...), cancel_message: str = Form("")):
    try:
        cancel_appointment(appointment_id)
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('SELECT phone, id FROM appointments WHERE id = ?', (appointment_id,))
        row = c.fetchone()
        conn.close()
        if row:
            phone, appt_id = row
            msg = f"Your appointment (Ref: {appt_id}) has been cancelled."
            if cancel_message.strip():
                msg += f"\n\nReason: {cancel_message}"
            msg += f"\n\nReply 'menu' to book a new appointment."
            send_message(phone, msg)
        return {"status": "ok", "message": "Appointment cancelled and patient notified"}
    except Exception as e:
        return {"status": "error", "message": str(e)}, 400

@app.post("/reschedule_appointment")
async def reschedule_appt(
    appointment_id: int = Form(...),
    new_date: str = Form(...),
    new_time: str = Form(...),
    reschedule_message: str = Form("")
):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('SELECT phone FROM appointments WHERE id = ?', (appointment_id,))
        row = c.fetchone()
        conn.close()
        if row:
            phone = row[0]
            reschedule_appointment(appointment_id, new_date, new_time)
            msg = f"Your appointment has been rescheduled.\n\nNew date: {new_date}\nNew time: {new_time}"
            if reschedule_message.strip():
                msg += f"\n\nNote from clinic: {reschedule_message}"
            send_message(phone, msg)
        return {"status": "ok", "message": "Appointment rescheduled and patient notified"}
    except Exception as e:
        return {"status": "error", "message": str(e)}, 400

@app.get("/api/available-times")
async def api_available_times(doctor_id: int, date: str):
    times = get_available_times(doctor_id, date)
    return {"times": times}

@app.post("/api/blocked-slot/add")
async def api_add_blocked_slot(
    doctor_id: int = Form(...),
    time: str = Form(...),
    date: str = Form(""),
    label: str = Form("Unavailable")
):
    add_blocked_slot(doctor_id, time, date or None, label)
    return {"status": "ok"}

@app.post("/api/blocked-slot/remove")
async def api_remove_blocked_slot(slot_id: int = Form(...)):
    remove_blocked_slot(slot_id)
    return {"status": "ok"}

@app.get("/api/blocked-slots/{doctor_id}")
async def api_get_blocked_slots(doctor_id: int):
    slots = get_blocked_slots(doctor_id)
    return {"slots": [{"id": s[0], "date": s[1], "time": s[2], "label": s[3]} for s in slots]}

@app.get("/export/appointments.csv")
async def export_appointments_csv(request: Request):
    from datetime import datetime as dt
    filter_hid = _get_filter_hospital_id(request)
    appointments = get_appointments(hospital_id=filter_hid)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Patient', 'Phone', 'Doctor', 'Date', 'Time', 'Status', 'Reminder Sent'])
    for a in appointments:
        writer.writerow([a[0], a[3], a[2], a[4], a[6], a[7], a[8], 'Yes' if a[9] else 'No'])
    output.seek(0)
    filename = f"appointments_{dt.now().strftime('%Y-%m-%d')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@app.post("/api/change-password")
async def api_change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...)
):
    username = getattr(request.state, 'username', None)
    if not username:
        return {"status": "error", "message": "Not authenticated"}
    user = get_clinic_user_by_username(username)
    if not user or not verify_password(current_password, user[3]):
        return {"status": "error", "message": "Current password is incorrect"}
    if new_password != confirm_password:
        return {"status": "error", "message": "Passwords do not match"}
    if len(new_password) < 6:
        return {"status": "error", "message": "Must be at least 6 characters"}
    update_clinic_user_password(username, _hash_password(new_password))
    return {"status": "ok"}

@app.get("/api/appointment/{appointment_id}")
async def get_appointment_detail(appointment_id: int):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''SELECT a.id, a.phone,
                            COALESCE(up.name, a.phone) AS patient_name,
                            d.name, d.specialty, h.name, a.date, a.time, a.status, a.doctor_id
                     FROM appointments a
                     JOIN doctors d ON a.doctor_id = d.id
                     JOIN hospitals h ON d.hospital_id = h.id
                     LEFT JOIN user_profiles up ON a.phone = up.phone
                     WHERE a.id = ?''', (appointment_id,))
        row = c.fetchone()
        conn.close()
        if row:
            return {
                "id": row[0],
                "phone": row[1],
                "patient_name": row[2],
                "doctor_name": row[3],
                "specialty": row[4],
                "hospital": row[5],
                "date": row[6],
                "time": row[7],
                "status": row[8],
                "doctor_id": row[9]
            }
        return {"error": "Appointment not found"}, 404
    except Exception as e:
        return {"error": str(e)}, 400

@app.get("/api/appointments-data")
async def get_appointments_data(request: Request):
    try:
        filter_hid = _get_filter_hospital_id(request)
        appointments = get_appointments(hospital_id=filter_hid)
        result = []
        for appt in appointments:
            result.append({
                "id": appt[0],
                "doctor_id": appt[1],
                "phone": appt[2],
                "patient_name": appt[3],
                "doctor_name": appt[4],
                "hospital": appt[5],
                "date": appt[6],
                "time": appt[7],
                "status": appt[8],
                "reminder_sent": appt[9]
            })
        return {
            "appointments": result,
            "count": len(result),
            "today_count": get_today_count(hospital_id=filter_hid),
            "upcoming_count": get_upcoming_count(hospital_id=filter_hid),
            "reminders_sent_today": get_reminders_sent_today(hospital_id=filter_hid),
        }
    except Exception as e:
        return {"error": str(e)}, 400

@app.get("/api/upcoming-appointments")
async def get_upcoming_appts(request: Request):
    from datetime import datetime, timedelta
    try:
        filter_hid = _get_filter_hospital_id(request)
        appointments = get_appointments(hospital_id=filter_hid)
        now = datetime.now()
        reaching_now = []
        for appt in appointments:
            appt_id, doctor_id, phone, patient_name, doctor_name, hospital, date, time_str, status, reminder_sent = appt
            try:
                appt_time = datetime.strptime(f"{date} {time_str}", "%Y-%m-%d %H:%M")
                minutes_until = (appt_time - now).total_seconds() / 60
                if 0 <= minutes_until <= 15:
                    reaching_now.append({
                        "id": appt_id,
                        "doctor": doctor_name,
                        "phone": phone,
                        "time": time_str,
                        "minutes_until": int(minutes_until),
                        "status": status
                    })
            except:
                continue
        return {"reaching": reaching_now}
    except Exception as e:
        print(f"Error getting upcoming appointments: {e}")
        return {"reaching": [], "error": str(e)}

@app.get("/api/debug")
async def debug_info(request: Request):
    filter_hid = _get_filter_hospital_id(request)
    appointments = get_appointments(hospital_id=filter_hid)
    return {
        "db_file": DB_FILE,
        "db_exists": os.path.exists(DB_FILE),
        "appointment_count": len(appointments),
        "appointments": [{"id": a[0], "phone": a[2], "date": a[6], "time": a[7], "status": a[8]} for a in appointments]
    }

@app.get("/api/clinic-settings")
async def get_clinic_settings(request: Request):
    try:
        filter_hid = _get_filter_hospital_id(request)
        hospitals = get_hospitals()
        doctors = get_doctors_all(hospital_id=filter_hid)
        clinic_name = _get_clinic_name(filter_hid)
        return {
            "clinic_name": clinic_name,
            "total_doctors": len(doctors),
            "active_doctors": sum(1 for d in doctors if d[4] == 1),
            "hours": {
                "open": "08:00",
                "close": "18:00"
            }
        }
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/clinic-settings")
async def update_clinic_settings(
    clinic_name: str = Form(None),
    open_time: str = Form(None),
    close_time: str = Form(None)
):
    return {"status": "ok", "message": "Settings saved"}

@app.post("/api/appointment/no-show")
async def mark_no_show_appt(request: Request):
    try:
        data = await request.json()
        appointment_id = data.get("appointment_id")
        if not appointment_id:
            return {"error": "No appointment ID provided"}
        mark_no_show(appointment_id)
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''SELECT a.phone, COALESCE(up.name, a.phone), d.name, a.date, a.time
                     FROM appointments a
                     JOIN doctors d ON a.doctor_id = d.id
                     LEFT JOIN user_profiles up ON a.phone = up.phone
                     WHERE a.id = ?''', (appointment_id,))
        row = c.fetchone()
        conn.close()
        if row:
            phone, patient_name, doc_name, date, appt_time = row
            first_name = patient_name.split()[0]
            msg = (f"Hi {first_name}, you missed your appointment with {doc_name} "
                   f"on {date} at {appt_time}.\n\n"
                   f"You can reschedule — reply 'menu' then choose option 2.\n\n"
                   f"This option is available for 24 hours.")
            send_message(phone, msg)
        return {"status": "ok", "message": "Appointment marked as no-show and patient notified"}
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/appointment/complete")
async def mark_appointment_complete(request: Request):
    try:
        data = await request.json()
        appointment_id = data.get("appointment_id")
        if not appointment_id:
            return {"error": "No appointment ID provided"}
        mark_appointment_completed(appointment_id)
        return {"status": "ok", "message": "Appointment marked as completed"}
    except Exception as e:
        return {"error": str(e)}

# ── Clinic management (superadmin only) ─────────────────────────────────────

@app.get("/api/clinics")
async def get_clinics(request: Request):
    if getattr(request.state, 'role', None) != 'superadmin':
        return JSONResponse({"error": "Forbidden"}, status_code=403)
    hospitals = get_hospitals()
    return {"clinics": [{"id": h[0], "name": h[1]} for h in hospitals]}

@app.post("/api/clinic/add")
async def api_add_clinic(request: Request, name: str = Form(...)):
    if getattr(request.state, 'role', None) != 'superadmin':
        return JSONResponse({"error": "Forbidden"}, status_code=403)
    name = name.strip()
    if not name:
        return {"status": "error", "message": "Clinic name cannot be empty"}
    try:
        new_id = add_hospital(name)
        return {"status": "ok", "id": new_id, "name": name}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ── Staff management (superadmin only) ──────────────────────────────────────

@app.get("/api/staff")
async def get_staff(request: Request):
    if getattr(request.state, 'role', None) != 'superadmin':
        return JSONResponse({"error": "Forbidden"}, status_code=403)
    users = list_clinic_users()
    return {"users": [{"id": u[0], "username": u[1], "role": u[2], "hospital_id": u[3], "hospital_name": u[4]} for u in users]}

@app.post("/api/staff/add")
async def add_staff(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form("admin"),
    hospital_id: int = Form(None)
):
    if getattr(request.state, 'role', None) != 'superadmin':
        return JSONResponse({"error": "Forbidden"}, status_code=403)
    try:
        create_clinic_user(username, password, role, hospital_id if hospital_id else None)
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/staff/delete")
async def remove_staff(request: Request, user_id: int = Form(...)):
    if getattr(request.state, 'role', None) != 'superadmin':
        return JSONResponse({"error": "Forbidden"}, status_code=403)
    delete_clinic_user(user_id)
    return {"status": "ok"}

# ── Scheduler ────────────────────────────────────────────────────────────────

scheduler = AsyncIOScheduler()

async def send_reminders():
    from datetime import datetime, timedelta
    try:
        cancel_old_no_shows()
    except Exception as e:
        print(f"Error cancelling old no-shows: {e}")

    try:
        appointments = get_upcoming_appointments(hours_ahead=24)
        now = datetime.now()
        for appt in appointments:
            appt_id, phone, doc_name, date, time = appt
            try:
                appt_datetime = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
            except:
                continue
            if appt_datetime.date() == now.date() and now.hour == 6:
                hospital_name = get_hospitals()[0][1] if get_hospitals() else "The Clinic"
                msg = (f"Appointment reminder - today.\n\n"
                       f"Time: {time}\nDoctor: {doc_name}\nClinic: {hospital_name}\n\n"
                       f"Bring your ID and arrive 10 minutes early.")
                send_message(phone, msg)
                mark_reminder_sent(appt_id)
    except Exception as e:
        print(f"Error sending reminders: {e}")
        import traceback
        traceback.print_exc()

@app.on_event("startup")
async def startup_event():
    scheduler.add_job(send_reminders, "interval", minutes=5)
    scheduler.start()
    print("Reminder scheduler started")

@app.on_event("shutdown")
async def shutdown_event():
    scheduler.shutdown()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
