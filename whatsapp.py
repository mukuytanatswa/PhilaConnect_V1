import requests
import os

TOKEN = os.getenv("WHATSAPP_TOKEN", "EAAcPr81TDkYBRKeyiKbusdTnaZAZAhrVxlOeWTCm5JDc8mpOPgCgXZBBsON2ZAtIMU7M9cWfdsbuFsxoqctWWYSWWXZAPVWzq2vCyaFT6ca9ZBCvcvdVwT8rZAZAJRLhJb7VWWVJLRHAqElOdCUg5hmSZAf2cG6CIEFdP18Mtnpw3gSJZBSd9VTgQ7P94cPBgjz8luSgZDZD")
PHONE_ID = os.getenv("WHATSAPP_PHONE_ID", "1056110920899451")


def send_list(phone, body_text, button_text, sections):
    """Send a WhatsApp interactive list message."""
    try:
        url = f"https://graph.facebook.com/v18.0/{PHONE_ID}/messages"
        headers = {
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": phone,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "body": {"text": body_text},
                "action": {
                    "button": button_text,
                    "sections": sections,
                },
            },
        }
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        if response.status_code != 200:
            print(f"WhatsApp List API error {response.status_code}: {response.text}")
            with open('whatsapp_errors.log', 'a') as f:
                f.write(f"List error to {phone}: {response.status_code}\n{response.text}\n")
        return response.status_code == 200
    except Exception as e:
        print(f"Error sending list to {phone}: {e}")
        with open('whatsapp_errors.log', 'a') as f:
            f.write(f"List exception to {phone}: {e}\n")
        return False


def send_message(phone, text):
    """Send a plain text WhatsApp message."""
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
        if response.status_code != 200:
            print(f"WhatsApp API error {response.status_code}: {response.text}")
            with open('whatsapp_errors.log', 'a') as f:
                f.write(f"Error sending to {phone}: {response.status_code}\n{response.text}\n")
        return response.status_code == 200
    except Exception as e:
        print(f"Error sending message to {phone}: {e}")
        with open('whatsapp_errors.log', 'a') as f:
            f.write(f"Exception sending to {phone}: {e}\n")
        return False
