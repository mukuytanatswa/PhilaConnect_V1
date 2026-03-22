import requests
import json

# Replace with your Meta WhatsApp credentials
TOKEN = "EAAcPr81TDkYBREZAXvAKbOYYOGJWeAIY2sFiHFCeOCPH8m9h9d3SvAssbTLEdvtOZBCJwrtrMpG2d0fumEdWrGDO8gYz6dcz1kSf7OiUGvYZCkowvoGKPf316b5JofegKJhfAUxlVO0VAZAPfXQt5d9GTZA7ScoIaLHQ14aTEM7yWWzRlnt0B6ycK5ZA3V5zY1tAZDZD"
PHONE_ID = "1056110920899451"

def send_message(phone, text):
    """Send message with error logging"""
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
            print(f"WhatsApp API Error: {response.status_code} - {response.text}")
            with open('whatsapp_errors.log', 'a') as f:
                f.write(f"Error sending to {phone}: {response.status_code}\n{response.text}\n")
        return response.status_code == 200
    except Exception as e:
        print(f"Error sending message to {phone}: {str(e)}")
        with open('whatsapp_errors.log', 'a') as f:
            f.write(f"Exception sending to {phone}: {str(e)}\n")
        return False
