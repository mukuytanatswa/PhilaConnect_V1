from whatsapp import send_message
from db import set_state, get_state, get_hospitals, get_doctors, get_available_dates, get_available_times, book_appointment, get_appointments, cancel_appointment
import sqlite3

def handle_message(data):
    try:
        # Extract phone number and text from WhatsApp payload
        message = data["entry"][0]["changes"][0]["value"]["messages"][0]
        phone = message["from"]
        text = message["text"]["body"].lower().strip()
    except:
        return

    state, data = get_state(phone)
    data = data or {}

    # Initial menu
    if text in ["hi", "hello", "hey"]:
        send_menu(phone)

    # User picked option 1 = Book appointment
    elif text == "1":
        send_hospitals(phone)

    # User picked option 2 = Reschedule
    elif text == "2":
        send_reschedule_options(phone)

    # User picked option 3 = Cancel
    elif text == "3":
        send_cancel_options(phone)

    # Handling hospital selection
    elif state == "select_hospital":
        try:
            hospital_id = int(text)
            hospitals = get_hospitals()
            if 1 <= hospital_id <= len(hospitals):
                data['hospital_id'] = hospitals[hospital_id-1][0]
                set_state(phone, "select_doctor", data)
                send_doctors(phone, data['hospital_id'])
            else:
                send_message(phone, "Invalid option. Please select a valid hospital number.")
        except ValueError:
            send_message(phone, "Please enter a number.")

    # Handling doctor selection
    elif state == "select_doctor":
        try:
            doctor_id = int(text)
            doctors = get_doctors(data['hospital_id'])
            if 1 <= doctor_id <= len(doctors):
                data['doctor_id'] = doctors[doctor_id-1][0]
                set_state(phone, "select_date", data)
                send_dates(phone, data['doctor_id'])
            else:
                send_message(phone, "Invalid option. Please select a valid doctor number.")
        except ValueError:
            send_message(phone, "Please enter a number.")

    # Handling date selection
    elif state == "select_date":
        try:
            date_index = int(text)
            dates = get_available_dates(data['doctor_id'])
            if 1 <= date_index <= len(dates):
                data['date'] = dates[date_index-1]
                set_state(phone, "select_time", data)
                send_times(phone, data['doctor_id'], data['date'])
            else:
                send_message(phone, "Invalid option. Please select a valid date number.")
        except ValueError:
            send_message(phone, "Please enter a number.")

    # Handling time selection
    elif state == "select_time":
        try:
            time_index = int(text)
            times = get_available_times(data['doctor_id'], data['date'])
            if 1 <= time_index <= len(times):
                data['time'] = times[time_index-1]
                # Book the appointment
                appointment_id = book_appointment(phone, data['doctor_id'], data['date'], data['time'])
                set_state(phone, None, {})  # Reset
                send_message(phone, f"✅ Your appointment is confirmed for {data['date']} at {data['time']}. Appointment ID: {appointment_id}")
            else:
                send_message(phone, "Invalid option. Please select a valid time number.")
        except ValueError:
            send_message(phone, "Please enter a number.")

    # Handling cancel selection
    elif state == "select_cancel":
        try:
            appointment_id = int(text)
            appointments = get_appointments(phone=phone)
            if 1 <= appointment_id <= len(appointments):
                cancel_appointment(appointments[appointment_id-1][0])
                set_state(phone, None, {})
                send_message(phone, "✅ Your appointment has been canceled.")
            else:
                send_message(phone, "Invalid option. Please select a valid appointment number.")
        except ValueError:
            send_message(phone, "Please enter a number.")

    # Handling reschedule selection
    elif state == "select_reschedule":
        try:
            appointment_id = int(text)
            appointments = get_appointments(phone=phone)
            if 1 <= appointment_id <= len(appointments):
                data['reschedule_id'] = appointments[appointment_id-1][0]
                data['doctor_id'] = appointments[appointment_id-1][1]
                set_state(phone, "reschedule_date", data)
                send_dates(phone, data['doctor_id'])
            else:
                send_message(phone, "Invalid option. Please select a valid appointment number.")
        except ValueError:
            send_message(phone, "Please enter a number.")

    # Handling reschedule date
    elif state == "reschedule_date":
        try:
            date_index = int(text)
            dates = get_available_dates(data['doctor_id'])  # Assuming doctor_id in data
            if 1 <= date_index <= len(dates):
                data['new_date'] = dates[date_index-1]
                set_state(phone, "reschedule_time", data)
                send_times(phone, data['doctor_id'], data['new_date'])
            else:
                send_message(phone, "Invalid option. Please select a valid date number.")
        except ValueError:
            send_message(phone, "Please enter a number.")

    # Handling reschedule time
    elif state == "reschedule_time":
        try:
            time_index = int(text)
            times = get_available_times(data['doctor_id'], data['new_date'])
            if 1 <= time_index <= len(times):
                data['new_time'] = times[time_index-1]
                # Update appointment
                conn = sqlite3.connect('philaconnect.db')
                c = conn.cursor()
                c.execute('UPDATE appointments SET date = ?, time = ? WHERE id = ?', (data['new_date'], data['new_time'], data['reschedule_id']))
                conn.commit()
                conn.close()
                set_state(phone, None, {})
                send_message(phone, f"✅ Your appointment has been rescheduled to {data['new_date']} at {data['new_time']}.")
            else:
                send_message(phone, "Invalid option. Please select a valid time number.")
        except ValueError:
            send_message(phone, "Please enter a number.")

    else:
        send_message(phone, "Sorry, I didn't understand that. Please reply with 'hi' to start.")

def send_menu(phone):
    send_message(
        phone,
        "Welcome to Philaconnect 👋\n\n"
        "Reply with:\n"
        "1️⃣ Book appointment\n"
        "2️⃣ Reschedule appointment\n"
        "3️⃣ Cancel appointment"
    )

def send_hospitals(phone):
    hospitals = get_hospitals()
    msg = "Select a hospital:\n"
    for i, (id, name) in enumerate(hospitals, 1):
        msg += f"{i}. {name}\n"
    send_message(phone, msg)
    set_state(phone, "select_hospital")

def send_doctors(phone, hospital_id):
    doctors = get_doctors(hospital_id)
    msg = "Select a doctor:\n"
    for i, (id, name, specialty) in enumerate(doctors, 1):
        msg += f"{i}. {name}\n   {specialty}\n"
    send_message(phone, msg)
    # State already set

def send_dates(phone, doctor_id):
    dates = get_available_dates(doctor_id)
    msg = "Select a date:\n"
    for i, date in enumerate(dates, 1):
        msg += f"{i}. {date}\n"
    send_message(phone, msg)
    # State already set

def send_times(phone, doctor_id, date):
    times = get_available_times(doctor_id, date)
    msg = "Select a time:\n"
    for i, time in enumerate(times, 1):
        msg += f"{i}. {time}\n"
    send_message(phone, msg)
    # State already set

def send_cancel_options(phone):
    appointments = get_appointments(phone=phone)
    if not appointments:
        send_message(phone, "You have no upcoming appointments to cancel.")
        return
    msg = "Select an appointment to cancel:\n"
    for i, (id, doctor_id, doc_name, specialty, hosp_name, date, time, status) in enumerate(appointments, 1):
        msg += f"{i}. {doc_name} ({specialty}) at {hosp_name} on {date} at {time}\n"
    send_message(phone, msg)
    set_state(phone, "select_cancel")

def send_reschedule_options(phone):
    appointments = get_appointments(phone=phone)
    if not appointments:
        send_message(phone, "You have no upcoming appointments to reschedule.")
        return
    msg = "Select an appointment to reschedule:\n"
    for i, (id, doctor_id, doc_name, specialty, hosp_name, date, time, status) in enumerate(appointments, 1):
        msg += f"{i}. {doc_name} ({specialty}) at {hosp_name} on {date} at {time}\n"
    send_message(phone, msg)
    set_state(phone, "select_reschedule")
