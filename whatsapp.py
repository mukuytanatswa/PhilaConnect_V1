import requests
import json
import os

# Get credentials from environment variables
TOKEN = os.getenv("WHATSAPP_TOKEN", "EAAcPr81TDkYBRB9p4ZAbVt1ptzPPDxwxved6nGrLF5ItE0oSO0MvdWbPoIDjsQlW0j2SY8ZC8h6T7lvueTTQcZA8hjx42IZBkZClQJoPuCsEGz2UoiSyMtcJw6AcFvgq4XRSWjkwQZB0Fri3VpCP8cvUEQBQjMlhwYfuhA7nTDCjJOp5RCWgXHNj7YBe2SdVNZCKQZDZD")
PHONE_ID = os.getenv("WHATSAPP_PHONE_ID", "1056110920899451")

def send_message(phone, text):
    """Send message with error logging"""
    print(f"Sending message to {phone}: {text[:50]}...")  # Debug log
    try:
        url = f"https://graph.facebook.com/v18.0/{PHONE_ID}/messages"
        headers = {
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": phone,
            "type": "text",
            "text": {"body": text},
        }
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        print(f"WhatsApp API response status: {response.status_code}")  # Debug
        if response.status_code != 200:
            print(f"WhatsApp API Error: {response.status_code} - {response.text}")
            with open('whatsapp_errors.log', 'a') as f:
                f.write(f"Error sending to {phone}: {response.status_code}\n{response.text}\n")
        else:
            print(f"Message sent successfully to {phone}")  # Debug
        return response.status_code == 200
    except Exception as e:
        print(f"Error sending message to {phone}: {str(e)}")
        with open('whatsapp_errors.log', 'a') as f:
            f.write(f"Exception sending to {phone}: {str(e)}\n")
        return False
