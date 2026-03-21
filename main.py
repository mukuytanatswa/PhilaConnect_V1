from fastapi import FastAPI, Request, Query, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from logic import handle_message
from db import get_appointments, toggle_doctor, get_doctors_all, get_hospitals, book_appointment, update_doctor_availability
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from whatsapp import send_message
from db import get_upcoming_appointments
import asyncio
import sqlite3

app = FastAPI()

# This is your verification token for Meta webhook
VERIFY_TOKEN = "philaconnect_verify"

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
        return templates.TemplateResponse("dashboard.html", {"request": request, "appointments": appointments, "doctors": doctors, "hospitals": hospitals})
    except Exception as e:
        # Log the error and return a simple error page
        print(f"Error loading dashboard: {e}")
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

# Scheduler for notifications
scheduler = AsyncIOScheduler()

async def send_reminders():
    from datetime import datetime, timedelta
    now = datetime.now()
    # 2 days before
    two_days = now + timedelta(days=2)
    appts = get_upcoming_appointments(48)
    for appt in appts:
        appt_id, phone, doc_name, date, time = appt
        appt_datetime = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
        if two_days.date() == appt_datetime.date() and appt_datetime.hour == 9:  # Morning
            send_message(phone, f"Reminder: You have an appointment with {doc_name} in 2 days on {date} at {time}.")
        elif (appt_datetime - now).days == 1 and appt_datetime.hour == 9:
            send_message(phone, f"Reminder: You have an appointment with {doc_name} tomorrow on {date} at {time}.")
        elif (appt_datetime - now).days == 0 and appt_datetime.hour == 9:
            send_message(phone, f"Reminder: You have an appointment with {doc_name} today at {time}.")
        elif (appt_datetime - now).total_seconds() / 3600 <= 0.5 and (appt_datetime - now).total_seconds() > 0:
            send_message(phone, f"Reminder: You have an appointment with {doc_name} in 30 minutes at {time}.")

# Start scheduler
@app.on_event("startup")
async def startup_event():
    scheduler.add_job(send_reminders, "interval", hours=1)  # Every hour
    scheduler.start()

@app.on_event("shutdown")
async def shutdown_event():
    scheduler.shutdown()
