from whatsapp import send_message
from db import set_state, get_state

def handle_message(data):
    try:
        # Extract phone number and text from WhatsApp payload
        message = data["entry"][0]["changes"][0]["value"]["messages"][0]
        phone = message["from"]
        text = message["text"]["body"].lower()
    except:
        return

    state = get_state(phone)

    # Initial menu
    if text in ["hi", "hello", "hey"]:
        send_menu(phone)

    # User picked option 1 = Book appointment
    elif text == "1":
        set_state(phone, "booking_service")
        send_message(phone, "What service do you need? (e.g. Therapy)")

    # User replied with the service
    elif state == "booking_service":
        set_state(phone, "booking_date")
        send_message(phone, "What date do you prefer? (YYYY-MM-DD)")

    # User replied with date
    elif state == "booking_date":
        set_state(phone, "booking_time")
        send_message(phone, "What time would you like? (HH:MM)")

    # User replied with time → confirm
    elif state == "booking_time":
        set_state(phone, None)  # Reset state
        send_message(phone, f"✅ Your appointment is confirmed! See you then.")

    # Cancel or other options
    elif text == "2":
        send_message(phone, "Cancel functionality will be added soon.")

def send_menu(phone):
    send_message(
        phone,
        "Welcome to Philaconnect 👋\n\n"
        "Reply with:\n"
        "1️⃣ Book appointment\n"
        "2️⃣ Cancel appointment"
    )
