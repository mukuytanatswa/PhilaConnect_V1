from fastapi import FastAPI, Request, Query, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from logic import handle_message
from db import get_appointments, toggle_doctor, get_doctors_all, get_hospitals, book_appointment, update_doctor_availability, cancel_appointment, get_user_profile, mark_appointment_completed, get_upcoming_appointments
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from whatsapp import send_message
import asyncio
import sqlite3
import json
import os

app = FastAPI()

# This is your verification token for Meta webhook
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "philaconnect_verify")

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
    print(f"Webhook received: {data}")  # Debug logging
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
        return templates.TemplateResponse("dashboard.html", {"request": request, "appointments": appointments, "doctors": doctors, "hospitals": hospitals, "active_doctors": active_doctors, "appt_counts": appt_counts})
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
    send_message(phone, f"Hello {patient_name}, your appointment at The Riverside Cottage is confirmed for {date} at {time} with {doctor_name}.")
    return RedirectResponse(url="/dashboard", status_code=303)

@app.post("/add_doctor")
async def add_doc(
    first_name: str = Form(...),
    surname: str = Form(...),
    specialty: str = Form("General Practice")
):
    name = f"Dr. {first_name} {surname}"
    hospital_id = get_hospitals()[0][0]  # Assume first hospital
    conn = sqlite3.connect('philaconnect.db')
    c = conn.cursor()
    c.execute('INSERT INTO doctors (name, specialty, hospital_id) VALUES (?, ?, ?)', (name, specialty, hospital_id))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/dashboard", status_code=303)

@app.post("/cancel_appointment")
async def cancel_appt(appointment_id: int = Form(...), cancel_message: str = Form("")):
    """Cancel an appointment and notify the patient"""
    try:
        cancel_appointment(appointment_id)
        # Get appointment details
        conn = sqlite3.connect('philaconnect.db')
        c = conn.cursor()
        c.execute('SELECT phone, id FROM appointments WHERE id = ?', (appointment_id,))
        row = c.fetchone()
        conn.close()
        
        if row:
            phone, appt_id = row
            msg = f"❌ Your appointment (ID: {appt_id}) has been cancelled."
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
        conn = sqlite3.connect('philaconnect.db')
        c = conn.cursor()
        c.execute('SELECT phone FROM appointments WHERE id = ?', (appointment_id,))
        row = c.fetchone()
        
        if row:
            phone = row[0]
            c.execute('UPDATE appointments SET date = ?, time = ? WHERE id = ?', (new_date, new_time, appointment_id))
            conn.commit()
            
            msg = f"📅 Your appointment has been rescheduled!\n\nNew Date: {new_date}\nNew Time: {new_time}"
            if reschedule_message.strip():
                msg += f"\n\nNote from clinic: {reschedule_message}"
            send_message(phone, msg)
        
        conn.close()
        return {"status": "ok", "message": "Appointment rescheduled and patient notified"}
    except Exception as e:
        return {"status": "error", "message": str(e)}, 400

@app.get("/api/appointment/{appointment_id}")
async def get_appointment_detail(appointment_id: int):
    """Get appointment details as JSON"""
    try:
        conn = sqlite3.connect('philaconnect.db')
        c = conn.cursor()
        c.execute('''SELECT a.id, a.phone, d.name, d.specialty, h.name, a.date, a.time, a.status
                     FROM appointments a
                     JOIN doctors d ON a.doctor_id = d.id
                     JOIN hospitals h ON d.hospital_id = h.id
                     WHERE a.id = ?''', (appointment_id,))
        row = c.fetchone()
        conn.close()
        
        if row:
            return {
                "id": row[0],
                "phone": row[1],
                "doctor_name": row[2],
                "specialty": row[3],
                "hospital": row[4],
                "date": row[5],
                "time": row[6],
                "status": row[7]
            }
        return {"error": "Appointment not found"}, 404
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
            appt_id, doctor_id, phone, doctor_name, hospital, date, time_str, status = appt
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
    
    try:
        appointments = get_upcoming_appointments(hours_ahead=48)
        now = datetime.now()
        
        for appt in appointments:
            appt_id, phone, doc_name, date, time = appt
            try:
                appt_datetime = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
            except:
                continue
            
            time_until_appt = appt_datetime - now
            hours_until = time_until_appt.total_seconds() / 3600
            
            # 48-hour reminder (send when within 49-47 hours)
            if 47 <= hours_until <= 49:
                hospital_name = get_hospitals()[0][1] if get_hospitals() else "The Clinic"
                msg = f"Sawubona 👋\n\nThis is a reminder of your appointment in 2 days.\n\n📅 {date}\n🕗 {time}\n👩‍⚕️ {doc_name}\n📍 {hospital_name}\n\nReply 'menu' to reschedule or with any questions. See you soon! ✅"
                send_message(phone, msg)
            
            # Morning-of reminder (send at 7 AM on the day of appointment)
            elif appt_datetime.date() == now.date() and 7 <= now.hour < 8:
                hospital_name = get_hospitals()[0][1] if get_hospitals() else "The Clinic"
                msg = f"Good morning ☀️\n\nQuick reminder - you have an appointment TODAY!\n\n🕗 {time}\n👩‍⚕️ {doc_name}\n📍 {hospital_name}\n\nPlease bring your ID and arrive 10 mins early. See you soon! ❤️"
                send_message(phone, msg)
            
            # 1-hour reminder (send when within 1.2-0.8 hours)
            elif 0.8 <= hours_until <= 1.2:
                hospital_name = get_hospitals()[0][1] if get_hospitals() else "The Clinic"
                msg = f"⏱ Your appointment is in 1 hour!\n\n🕗 {time}\n👩‍⚕️ {doc_name}\n📍 {hospital_name}\n\nRunning late? Reply immediately so we can help. See you soon! ❤️"
                send_message(phone, msg)
    
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
