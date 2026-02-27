from fastapi import FastAPI, Request, Query
from logic import handle_message

app = FastAPI()

# This is your verification token for Meta webhook
VERIFY_TOKEN = "philaconnect_verify"

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
