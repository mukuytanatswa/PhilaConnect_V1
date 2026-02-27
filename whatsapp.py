import requests

# Replace with your Meta WhatsApp credentials
TOKEN = "YOUR_WHATSAPP_TOKEN"
PHONE_ID = "YOUR_PHONE_NUMBER_ID"

def send_message(phone, text):
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
    requests.post(url, headers=headers, json=payload)
