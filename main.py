from fastapi import FastAPI, Request, Query, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from logic import handle_message
from db import get_appointments, toggle_doctor, get_doctors_all, get_hospitals, book_appointment, update_doctor_availability, cancel_appointment, reschedule_appointment, get_user_profile, mark_appointment_completed, mark_no_show, cancel_old_no_shows, get_upcoming_appointments, mark_reminder_sent, get_today_count, get_yesterday_count, get_reminders_sent_today, get_upcoming_count, DB_FILE
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from whatsapp import send_message
import asyncio
import sqlite3
import json
import os

app = FastAPI()

# This is your verification token for Meta webhook
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "philaconnect_verify")
CLINIC_NAME = os.getenv("CLINIC_NAME", "PhilaConnect Clinic")

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
    data = await request.json()
    handle_message(data)
    return {"status": "ok"}

# Dashboard
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    try:
        appointments = get_appointments()
        doctors = get_doctors_all()
        hospitals = get_hospitals()
        active_doctors = sum(1 for doc in doctors if doc[4] == 1)
        # Count appointments per doctor
        appt_counts = {}
        for appt in appointments:
            doc_id = appt[1]
            appt_counts[doc_id] = appt_counts.get(doc_id, 0) + 1
        today_count = get_today_count()
        yesterday_count = get_yesterday_count()
        reminders_sent_today = get_reminders_sent_today()
        upcoming_count = get_upcoming_count()
        booked_count = sum(1 for a in appointments if a[8] == 'booked')
        rescheduled_count = sum(1 for a in appointments if a[8] == 'rescheduled')
        cancelled_count = sum(1 for a in appointments if a[8] == 'cancelled')
        no_show_count = sum(1 for a in appointments if a[8] == 'no_show')
        return templates.TemplateResponse(request, "dashboard.html", {
            "appointments": appointments,
            "doctors": doctors,
            "hospitals": hospitals,
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
        })
    except Exception as e:
        # Log the error and return a simple error page
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
    patient_name: str = Form(...),
    phone: str = Form(...),
    date: str = Form(...),
    time: str = Form(...),
    doctor_id: int = Form(...),
    type: str = Form("General Consultation"),
    notes: str = Form("")
):
    appointment_id = book_appointment(phone, doctor_id, date, time)
    # Get doctor name
    doctors = get_doctors_all()
    doctor_name = next((d[1] for d in doctors if d[0] == doctor_id), "Doctor")
    # Send confirmation message
    send_message(phone, f"Hello {patient_name}, your appointment at {CLINIC_NAME} is confirmed for {date} at {time} with {doctor_name}.")
    return RedirectResponse(url="/dashboard", status_code=303)

@app.post("/add_doctor")
async def add_doc(
    first_name: str = Form(...),
    surname: str = Form(...),
    specialty: str = Form("General Practice")
):
    name = f"Dr. {first_name} {surname}"
    hospital_id = get_hospitals()[0][0]  # Assume first hospital
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('INSERT INTO doctors (name, specialty, hospital_id, available_days) VALUES (?, ?, ?, ?)', (name, specialty, hospital_id, 'Mon,Tue,Wed,Thu,Fri'))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/dashboard", status_code=303)

@app.post("/cancel_appointment")
async def cancel_appt(appointment_id: int = Form(...), cancel_message: str = Form("")):
    """Cancel an appointment and notify the patient"""
    try:
        cancel_appointment(appointment_id)
        # Get appointment details
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
    """Reschedule an appointment and notify the patient"""
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

@app.get("/api/appointment/{appointment_id}")
async def get_appointment_detail(appointment_id: int):
    """Get appointment details as JSON"""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''SELECT a.id, a.phone,
                            COALESCE(up.name, a.phone) AS patient_name,
                            d.name, d.specialty, h.name, a.date, a.time, a.status
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
                "status": row[8]
            }
        return {"error": "Appointment not found"}, 404
    except Exception as e:
        return {"error": str(e)}, 400

@app.get("/api/appointments-data")
async def get_appointments_data():
    """Get all appointments as JSON for dashboard refresh"""
    try:
        appointments = get_appointments()
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
        return {"appointments": result, "count": len(result)}
    except Exception as e:
        return {"error": str(e)}, 400

@app.get("/api/upcoming-appointments")
async def get_upcoming_appts():
    """Get appointments reaching their time (for alerts)"""
    from datetime import datetime, timedelta
    try:
        # Get all current appointments
        appointments = get_appointments()
        now = datetime.now()
        
        reaching_now = []  # Appointments in the next 15 minutes
        completed = []      # Appointments that just passed
        
        for appt in appointments:
            appt_id, doctor_id, phone, patient_name, doctor_name, hospital, date, time_str, status, reminder_sent = appt
            try:
                appt_time = datetime.strptime(f"{date} {time_str}", "%Y-%m-%d %H:%M")
                minutes_until = (appt_time - now).total_seconds() / 60
                
                # Alert if appointment is in next 15 minutes
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
async def debug_info():
    """Show which DB file the server is using and current appointment count"""
    import os
    appointments = get_appointments()
    return {
        "db_file": DB_FILE,
        "db_exists": os.path.exists(DB_FILE),
        "appointment_count": len(appointments),
        "appointments": [{"id": a[0], "phone": a[2], "date": a[6], "time": a[7], "status": a[8]} for a in appointments]
    }

@app.get("/api/clinic-settings")
async def get_clinic_settings():
    """Get clinic settings"""
    try:
        hospitals = get_hospitals()
        doctors = get_doctors_all()
        return {
            "clinic_name": hospitals[0][1] if hospitals else "PhilaConnect Clinic",
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
    """Update clinic settings (for Settings page)"""
    # For now, just return success - implement full settings later
    return {"status": "ok", "message": "Settings saved"}

@app.post("/api/appointment/no-show")
async def mark_no_show_appt(request: Request):
    """Mark an appointment as no-show and notify the patient"""
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
    """Mark an appointment as completed when notified"""
    try:
        data = await request.json()
        appointment_id = data.get("appointment_id")
        if not appointment_id:
            return {"error": "No appointment ID provided"}
        
        # Mark as completed in database
        mark_appointment_completed(appointment_id)
        
        return {"status": "ok", "message": "Appointment marked as completed"}
    except Exception as e:
        return {"error": str(e)}

# Scheduler for notifications
scheduler = AsyncIOScheduler()

async def send_reminders():
    """Send reminders at the appropriate times"""
    from datetime import datetime, timedelta

    # Auto-cancel no-show appointments older than 24 hours
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

            # Single reminder: 6am on the morning of the appointment
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

# Start scheduler
@app.on_event("startup")
async def startup_event():
    scheduler.add_job(send_reminders, "interval", minutes=5)  # Every 5 minutes to catch reminders accurately
    scheduler.start()
    print("Reminder scheduler started")

@app.on_event("shutdown")
async def shutdown_event():
    scheduler.shutdown()

# Start the server
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
