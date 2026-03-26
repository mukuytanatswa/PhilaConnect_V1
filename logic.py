from whatsapp import send_message, send_list
from db import set_state, get_state, get_hospitals, get_doctors, get_doctors_all, get_available_dates, get_available_times, book_appointment, get_appointments, cancel_appointment, get_user_profile, set_user_profile
import sqlite3
from datetime import datetime

def handle_message(data):
    try:
        # Extract phone number and text from WhatsApp payload
        message = data.get("entry", [{}])[0].get("changes", [{}])[0].get("value", {}).get("messages", [])
        if not message:
            print("No messages in payload")
            return
        
        message = message[0]
        phone = message.get("from")
        
        # Handle different message types
        if message.get("type") == "text":
            text = message.get("text", {}).get("body", "").lower().strip()
        elif message.get("type") == "interactive":
            interactive = message.get("interactive", {})
            if "button_reply" in interactive:
                text = interactive["button_reply"].get("id", "").lower().strip()
            elif "list_reply" in interactive:
                text = interactive["list_reply"].get("id", "").lower().strip()
            else:
                return
        else:
            print(f"Unsupported message type: {message.get('type')}")
            return
        
        if not phone or not text:
            print(f"Missing phone or text: phone={phone}, text={text}")
            return
        
        print(f"Processing message from {phone}: {text}")
        
    except Exception as e:
        print(f"Error extracting message: {str(e)}")
        import traceback
        traceback.print_exc()
        return

    state, data = get_state(phone)
    data = data or {}

    # Check for trigger words at ANY point to allow exit from any state
    greetings = ["hi", "hello", "hey", "menu", "start", "help"]
    if text.lower() in greetings:
        send_menu(phone)
        set_state(phone, None, {})  # Reset state to idle
        return

    # User picked option 1 = Book appointment
    if text == "1" and (state is None or state == "idle"):
        send_hospitals(phone)
        return

    # User picked option 2 = Reschedule
    if text == "2" and (state is None or state == "idle"):
        send_reschedule_options(phone)
        return

    # User picked option 3 = Cancel
    if text == "3" and (state is None or state == "idle"):
        send_cancel_options(phone)
        return
    
    # User picked option 4 = Change User Info
    if text == "4" and (state is None or state == "idle"):
        set_state(phone, "update_user_info", {})
        send_message(phone, "📝 Update Your Information\n\nWhat would you like to update?\n\n1️⃣ Name\n2️⃣ Phone Number\n3️⃣ Back to Menu")
        return

    # Handling hospital selection
    if state == "select_hospital":
        try:
            hospital_id = int(text)
            hospitals = get_hospitals()
            if not hospitals:
                send_message(phone, "No hospitals are configured yet. Please contact admin.")
                set_state(phone, None, {})
                return
            if 1 <= hospital_id <= len(hospitals):
                data['hospital_id'] = hospitals[hospital_id-1][0]
                set_state(phone, "select_doctor", data)
                send_doctors(phone, data['hospital_id'], data)
            else:
                send_message(phone, "Invalid option. Please select a valid hospital number.")
        except ValueError:
            send_message(phone, "Please enter a number.")

    # Handling doctor selection
    elif state == "select_doctor":
        hospital_id = data.get('hospital_id')
        doctors = get_doctors(hospital_id) if hospital_id else []

        if not doctors:
            send_message(phone, "No doctors available for the selected hospital. Please reply 'hi' to restart.")
            set_state(phone, None, {})
            return

        selected_id = None
        try:
            doctor_index = int(text)
            if 1 <= doctor_index <= len(doctors):
                selected_id = doctors[doctor_index-1][0]
            else:
                send_message(phone, f"Invalid number. Pick 1..{len(doctors)}.")
                return
        except ValueError:
            # allow typing doctor name too
            matches = [d for d in doctors if text.lower() in d[1].lower()]
            if len(matches) == 1:
                selected_id = matches[0][0]
            elif len(matches) > 1:
                names = ', '.join(d[1] for d in matches)
                send_message(phone, f"Multiple match: {names}. Please reply with the number from the list.")
                return
            else:
                send_message(phone, "Please reply with doctor number or exact doctor name.")
                return

        if selected_id is not None:
            data['doctor_id'] = selected_id
            send_date_list(phone, data['doctor_id'], data)
        else:
            send_message(phone, "Could not find the chosen doctor. Reply with number or name.")

    # Handling date selection
    elif state == "select_date":
        if text.startswith('date_'):
            date = text.replace('date_', '')
            import re
            if re.match(r'^\d{4}-\d{2}-\d{2}$', date):
                data['date'] = date
                set_state(phone, "select_time", data)
                send_time_list(phone, data['doctor_id'], data['date'], data)
            else:
                send_message(phone, "Invalid date. Please select from the list.")
        else:
            send_message(phone, "Please select a date from the list.")

    # Handling time selection
    elif state == "select_time":
        if text.startswith('time_'):
            time = text.replace('time_', '')
            times = get_available_times(data['doctor_id'], data['date'])
            if time in times:
                data['time'] = time
                appointment_id = book_appointment(phone, data['doctor_id'], data['date'], data['time'])
                set_state(phone, None, {})
                date_obj = datetime.strptime(data['date'], '%Y-%m-%d')
                date_label = date_obj.strftime('%A, %d %B %Y')
                send_message(phone, f"✅ APPOINTMENT CONFIRMED\n\nDate: {date_label}\nTime: {_fmt_time(time)}\nRef ID: {appointment_id}\n\nReply 'menu' to return to the main menu.")
            else:
                send_message(phone, "Invalid selection. Please choose from the list.")
        else:
            send_message(phone, "Please select a time from the list.")


    # Handling cancel selection
    elif state == "select_cancel":
        try:
            appointment_id = int(text)
            appointments = get_appointments(phone=phone)
            if 1 <= appointment_id <= len(appointments):
                cancel_appointment(appointments[appointment_id-1][0])
                set_state(phone, None, {})
                send_message(phone, "APPOINTMENT CANCELED\n\nYour appointment has been canceled. You can book a new one anytime.")
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
                send_date_list(phone, data['doctor_id'], data)
            else:
                send_message(phone, "Invalid option. Please select a valid appointment number.")
        except ValueError:
            send_message(phone, "Please enter a number.")

    # Handling reschedule date
    elif state == "reschedule_date":
        if text.startswith('date_'):
            date = text.replace('date_', '')
            import re
            if re.match(r'^\d{4}-\d{2}-\d{2}$', date):
                data['new_date'] = date
                set_state(phone, "reschedule_time", data)
                send_time_list(phone, data['doctor_id'], data['new_date'], data, prefix='rtime')
            else:
                send_message(phone, "Invalid date. Please select from the list.")
        else:
            send_message(phone, "Please select a date from the list.")

    # Handling reschedule time
    elif state == "reschedule_time":
        if text.startswith('rtime_'):
            time = text.replace('rtime_', '')
            times = get_available_times(data['doctor_id'], data['new_date'])
            if time in times:
                data['new_time'] = time
                conn = sqlite3.connect('philaconnect.db')
                c = conn.cursor()
                c.execute('UPDATE appointments SET status = "cancelled" WHERE id = ?', (data['reschedule_id'],))
                c.execute('INSERT INTO appointments (phone, doctor_id, date, time, status) VALUES (?, ?, ?, ?, "booked")',
                         (phone, data['doctor_id'], data['new_date'], data['new_time']))
                conn.commit()
                conn.close()
                set_state(phone, None, {})
                date_obj = datetime.strptime(data['new_date'], '%Y-%m-%d')
                date_label = date_obj.strftime('%A, %d %B %Y')
                send_message(phone, f"✅ APPOINTMENT RESCHEDULED\n\nNew Date: {date_label}\nNew Time: {_fmt_time(data['new_time'])}\n\nReply 'menu' to return to the main menu.")
            else:
                send_message(phone, "Invalid selection. Please choose from the list.")
        else:
            send_message(phone, "Please select a time from the list.")
    
    # Handling user info update
    elif state == "update_user_info":
        if text == "1":
            set_state(phone, "update_name", {})
            send_message(phone, "📝 What is your name?")
        elif text == "2":
            set_state(phone, "update_phone", {})
            send_message(phone, "📝 What is your phone number? (Format: +27XXXXXXXXX)")
        elif text == "3":
            set_state(phone, None, {})
            send_menu(phone)
        else:
            send_message(phone, "Invalid option. Please reply 1, 2, or 3.")
    
    elif state == "update_name":
        # Store the name in database
        name = text.strip()
        set_user_profile(phone, name)
        set_state(phone, None, {})
        send_message(phone, f"✅ Your name has been updated to: {name}\n\nReply 'menu' to return to the main menu.")
    
    elif state == "update_phone":
        # Store the phone in user data (note: phone number itself is the key)
        if text.startswith('+27') and len(text) >= 12:
            # Just acknowledge, the key is already the phone number
            set_state(phone, None, {})
            send_message(phone, f"✅ Phone number confirmed!\n\nReply 'menu' to return to the main menu.")
        else:
            send_message(phone, "❌ Invalid format. Please use format +27XXXXXXXXX")

    else:
        # Don't send unhelpful message, just ignore
        pass

def send_menu(phone):
    send_message(
        phone,
        "Welcome to PhilaConnect 👋\n\n"
        "Reply with:\n"
        "1️⃣ Book appointment\n"
        "2️⃣ Reschedule appointment\n"
        "3️⃣ Cancel appointment\n"
        "4️⃣ Update my information"
    )

def send_hospitals(phone):
    hospitals = get_hospitals()
    msg = "Select a hospital:\n"
    for i, (id, name) in enumerate(hospitals, 1):
        msg += f"{i}. {name}\n"
    send_message(phone, msg)
    set_state(phone, "select_hospital")

def send_doctors(phone, hospital_id, context=None):
    doctors = get_doctors(hospital_id)

    base_context = dict(context or {})
    base_context['hospital_id'] = hospital_id

    if not doctors:
        send_message(phone, "No doctors are currently available at this hospital. Please select another hospital or reply 'hi' to restart.")
        set_state(phone, None, {})
        return

    msg = "DOCTOR LIST (choose by number):\n\n"
    for i, (id, name, specialty, available_days) in enumerate(doctors, 1):
        msg += f"{i}. {name} | {specialty} | Days: {available_days}\n"
    msg += "\nReply with the doctor number (e.g., 1)."
    send_message(phone, msg)
    set_state(phone, "select_doctor", context or {})

def _fmt_time(t):
    """Format 24h time string as '9:00 AM' / '2:00 PM'"""
    h, m = map(int, t.split(':'))
    period = 'AM' if h < 12 else 'PM'
    hour12 = 12 if h == 0 else h - 12 if h > 12 else h
    return f"{hour12}:{m:02d} {period}"


def send_date_list(phone, doctor_id, context=None):
    """Send dates as a scrollable WhatsApp interactive list, grouped by week."""
    from datetime import timedelta
    dates = get_available_dates(doctor_id)
    if not dates:
        send_message(phone, "No available dates for this doctor.")
        set_state(phone, None)
        return

    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    days_until_monday = (7 - today.weekday()) % 7 or 7
    next_monday = today + timedelta(days=days_until_monday)
    following_monday = next_monday + timedelta(days=7)

    this_week, next_week, later = [], [], []
    for d in dates:
        date_obj = datetime.strptime(d, '%Y-%m-%d')
        if date_obj < next_monday:
            this_week.append(d)
        elif date_obj < following_monday:
            next_week.append(d)
        else:
            later.append(d)

    def make_rows(date_list):
        rows = []
        for d in date_list:
            date_obj = datetime.strptime(d, '%Y-%m-%d')
            diff = (date_obj - today).days
            title = f"{date_obj.strftime('%a')} {date_obj.day} {date_obj.strftime('%b')}"
            if diff == 1:
                desc = "Tomorrow"
            elif diff <= 6:
                desc = f"This {date_obj.strftime('%A')}"
            else:
                desc = date_obj.strftime('%d %B %Y')
            rows.append({"id": f"date_{d}", "title": title, "description": desc})
        return rows

    sections = []
    if this_week:
        sections.append({"title": "This Week", "rows": make_rows(this_week)})
    if next_week:
        sections.append({"title": "Next Week", "rows": make_rows(next_week)})
    if later:
        sections.append({"title": "Upcoming", "rows": make_rows(later)})

    data = dict(context or {})
    set_state(phone, 'select_date', data)
    send_list(phone, "📅 Scroll and choose an appointment date:", "View Dates", sections)


def send_time_list(phone, doctor_id, date, context=None, prefix='time'):
    """Send time slots as a scrollable WhatsApp interactive list, grouped by AM/PM."""
    times = get_available_times(doctor_id, date)
    morning = [t for t in times if int(t.split(':')[0]) < 12]
    afternoon = [t for t in times if int(t.split(':')[0]) >= 12]

    sections = []
    if morning:
        sections.append({
            "title": "Morning ☀️",
            "rows": [{"id": f"{prefix}_{t}", "title": _fmt_time(t), "description": "Available"} for t in morning],
        })
    if afternoon:
        sections.append({
            "title": "Afternoon 🌤️",
            "rows": [{"id": f"{prefix}_{t}", "title": _fmt_time(t), "description": "Available"} for t in afternoon],
        })

    date_obj = datetime.strptime(date, '%Y-%m-%d')
    date_label = f"{date_obj.strftime('%a')} {date_obj.day} {date_obj.strftime('%b')}"

    data = dict(context or {})
    set_state(phone, 'select_time', data)
    send_list(phone, f"📅 Date: {date_label}\n\n🕐 Scroll and pick a time slot:", "View Times", sections)


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
