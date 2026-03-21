import requests

# Replace with your Meta WhatsApp credentials
TOKEN = "EAAcPr81TDkYBREZAXvAKbOYYOGJWeAIY2sFiHFCeOCPH8m9h9d3SvAssbTLEdvtOZBCJwrtrMpG2d0fumEdWrGDO8gYz6dcz1kSf7OiUGvYZCkowvoGKPf316b5JofegKJhfAUxlVO0VAZAPfXQt5d9GTZA7ScoIaLHQ14aTEM7yWWzRlnt0B6ycK5ZA3V5zY1tAZDZD"
PHONE_ID = "1056110920899451"

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
