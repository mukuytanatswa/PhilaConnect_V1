from whatsapp import send_message
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
            # Use new combined date+time picker by default
            send_combined_date_time(phone, data['doctor_id'])
        else:
            send_message(phone, "Could not find the chosen doctor. Reply with number or name.")

    # Handling date selection
    elif state == "select_date":
        try:
            choice = int(text)
            date_to_option = data.get('date_to_option', {})
            if choice in date_to_option:
                data['date'] = date_to_option[choice]
                set_state(phone, "select_time", data)
                send_times(phone, data['doctor_id'], data['date'], data)
            else:
                send_message(phone, "Invalid selection. Please reply with a date number shown in the calendar.")
        except ValueError:
            send_message(phone, "Please reply with a number for your preferred date.")

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
                send_message(phone, f"APPOINTMENT CONFIRMED\n\nDate: {data['date']}\nTime: {data['time']}\nAppointment ID: {appointment_id}\n\nCheck your dashboard for details.")
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
                # Mark old appointment as cancelled and create a new one
                conn = sqlite3.connect('philaconnect.db')
                c = conn.cursor()
                # Cancel the old appointment
                c.execute('UPDATE appointments SET status = "cancelled" WHERE id = ?', (data['reschedule_id'],))
                # Create a new appointment with the new date/time
                c.execute('INSERT INTO appointments (phone, doctor_id, date, time, status) VALUES (?, ?, ?, ?, "booked")', 
                         (phone, data['doctor_id'], data['new_date'], data['new_time']))
                conn.commit()
                conn.close()
                set_state(phone, None, {})
                send_message(phone, f"APPOINTMENT RESCHEDULED\n\nNew Date: {data['new_date']}\nNew Time: {data['new_time']}")
            else:
                send_message(phone, "Invalid option. Please select a valid time number.")
        except ValueError:
            send_message(phone, "Please enter a number.")
    
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

def send_dates(phone, doctor_id, page=0):
    dates = get_available_dates(doctor_id)
    page_size = 7
    total = len(dates)
    if total == 0:
        send_message(phone, "No available dates for this doctor.")
        set_state(phone, None)
        return

    start = page * page_size
    end = start + page_size
    page_dates = dates[start:end]
    if not page_dates:
        send_message(phone, "No more dates available. Reply with 1..7 or 'hi' to restart.")
        return

    msg = f"📅 SELECT DATE (page {page+1}/{(total+page_size-1)//page_size}):\n"
    msg += "═" * 40 + "\n"
    for i, date in enumerate(page_dates, 1):
        day_obj = datetime.strptime(date, '%Y-%m-%d')
        day_name = day_obj.strftime('%A')
        msg += f"{i}. {day_name.upper()} · {date}\n"
    if end < total:
        msg += "\nReply with number 1-7, or text 'MORE' for next set of dates."
    else:
        msg += "\nReply with number 1-7 to pick your date."

    data = get_state(phone)[1] or {}
    data['date_page'] = page
    set_state(phone, 'select_date', data)
    send_message(phone, msg)

def send_times(phone, doctor_id, date, context=None):
    times = get_available_times(doctor_id, date)
    
    # Group times by period (AM/PM)
    am_times = [t for t in times if int(t.split(':')[0]) < 12]
    pm_times = [t for t in times if int(t.split(':')[0]) >= 12]
    
    msg = "🕐 SELECT TIME:\n" + "═" * 40 + "\n"
    
    if am_times:
        msg += "MORNING ☀️\n"
        for i, time in enumerate(am_times, 1):
            msg += f"  {i}. {time} AM\n"
        msg += "\n"
    
    if pm_times:
        msg += "AFTERNOON 🌤️\n"
        start_idx = len(am_times) + 1
        for i, time in enumerate(pm_times, 1):
            msg += f"  {start_idx + i - 1}. {time} PM\n"
    
    msg += "\nReply with the number for your preferred time"
    send_message(phone, msg)
    set_state(phone, "select_time", context or {})

def send_combined_date_time(phone, doctor_id, page=0):
    """Calendar grid date picker - keep dates separate from times"""
    dates = get_available_dates(doctor_id)
    if not dates:
        send_message(phone, "No available dates for this doctor.")
        set_state(phone, None)
        return

    # Group dates by month for calendar display
    from collections import defaultdict
    dates_by_month = defaultdict(list)
    for date_str in dates:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        month_key = date_obj.strftime('%Y-%m')
        dates_by_month[month_key].append((date_str, date_obj))
    
    # Get first month's dates
    first_month_key = sorted(dates_by_month.keys())[0]
    month_dates = sorted(dates_by_month[first_month_key], key=lambda x: x[1])
    first_date = month_dates[0][1]
    
    # Build calendar grid
    month_name = first_date.strftime('%B %Y')
    days_of_week = ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su']
    
    # Get first day of month
    first_day_weekday = first_date.replace(day=1).weekday()  # Monday=0, Sunday=6
    
    msg = f"📅 {month_name}\n"
    msg += " ".join(days_of_week) + "\n"
    msg += "─" * 26 + "\n"
    
    # Add empty cells before first day
    grid_day = 1
    week = [" " * 2] * first_day_weekday
    
    date_to_option = {}  # Map displayed number to actual date
    option_num = 1
    
    # Get all days in the month
    if first_month_key == sorted(dates_by_month.keys())[-1]:
        # Last month, only show available dates
        month_days = [d[0] for d in month_dates]
    else:
        # Full month
        last_day = 31
        for day in range(1, 32):
            try:
                first_date.replace(day=day)
            except ValueError:
                last_day = day - 1
                break
        month_days = [d[0] for d in month_dates]
    
    # Build the calendar grid
    day_counter = 1
    for date_str, date_obj in month_dates:
        day_num = date_obj.day
        
        # Pad with spaces if needed
        while len(week) < 7 and day_counter > 1:
            week.append(" " * 2)
        
        if len(week) == 7:
            msg += " ".join(f"{d:>2}" for d in week) + "\n"
            week = []
        
        week.append(f"{option_num:>2}")
        date_to_option[option_num] = date_str
        option_num += 1
        day_counter += 1
    
    # Pad last week
    while len(week) < 7:
        week.append(" " * 2)
    msg += " ".join(f"{d:>2}" for d in week) + "\n"
    
    msg += "─" * 26 + "\n"
    msg += "Reply with the number for your preferred date."
    
    data = get_state(phone)[1] or {}
    data['date_to_option'] = date_to_option
    set_state(phone, 'select_date', data)
    send_message(phone, msg)

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
