# PhilaConnect WhatsApp Bot – Complete Setup Guide

Your phone number: **0746264454** (formatted for WhatsApp API: **27746264454**)

---

## OVERVIEW

You will:
1. Create a Meta Developer account and WhatsApp app
2. Deploy the bot code to a server (Railway – free)
3. Connect the webhook
4. Test it on WhatsApp

Total time: ~45–60 minutes

---

## PHASE 1: META DEVELOPER SETUP

### Step 1 – Create a Meta Developer Account

1. Go to **https://developers.facebook.com**
2. Click **"Get Started"** (top right)
3. Log in with a Facebook account (or create one)
4. Verify your account with your phone number

### Step 2 – Create a New App

1. Go to **https://developers.facebook.com/apps**
2. Click **"Create App"**
3. Select **"Business"** as the app type → click Next
4. Fill in:
   - **App Name:** PhilaConnect
   - **App Contact Email:** your email
5. Click **"Create App"**

### Step 3 – Add WhatsApp to Your App

1. On your app dashboard, scroll down to find **"WhatsApp"**
2. Click **"Set Up"** under WhatsApp
3. You'll land on the WhatsApp Getting Started page

### Step 4 – Set Up WhatsApp Business Account

1. Under "Step 1: Select a business portfolio", click **"Create new business portfolio"**
   - Business Name: PhilaConnect
   - Click **"Continue"**
2. You'll see a **Test phone number** assigned automatically (e.g. +1 555 ...)
   - ⚠️ This is for testing only
3. Scroll down – you'll see **"Step 2: Send and receive messages"**
4. Under **"To"**, click the dropdown and add your number: **+27746264454**
5. Click **"Send message"** – you'll get a test message on your WhatsApp

### Step 5 – Get Your Credentials

Still on the WhatsApp Getting Started page:

1. **Phone Number ID** – copy it (looks like: `123456789012345`)
   - Save this as: `WHATSAPP_PHONE_NUMBER_ID`

2. **Temporary Access Token** – click **"Generate token"** – copy it
   - Save this as: `WHATSAPP_ACCESS_TOKEN`
   - ⚠️ This expires in 24 hours. We'll get a permanent one after testing.

---

## PHASE 2: DEPLOY THE BOT TO RAILWAY (FREE HOSTING)

### Step 6 – Install Node.js (if not installed)

Download from: **https://nodejs.org** (install the LTS version)

### Step 7 – Set Up the Project

Open your terminal/command prompt and run:

```bash
mkdir philaconnect
cd philaconnect
```

Copy all the provided code files into this folder:
- `index.js`
- `bot.js`
- `whatsapp.js`
- `db.js`
- `package.json`
- `.env.example`
- `Procfile`

Then rename `.env.example` to `.env` and fill in your values:

```
WHATSAPP_ACCESS_TOKEN=paste_your_token_here
WHATSAPP_PHONE_NUMBER_ID=paste_your_phone_number_id_here
VERIFY_TOKEN=philaconnect_secret_2024
PORT=3000
```

Install dependencies:
```bash
npm install
```

Test it locally:
```bash
node index.js
# Should say: 🚀 PhilaConnect running on port 3000
```

### Step 8 – Push to GitHub

1. Go to **https://github.com** and create a free account if needed
2. Click **"New Repository"** → name it `philaconnect` → click **"Create"**
3. In your terminal (inside the philaconnect folder):

```bash
git init
git add .
git commit -m "Initial PhilaConnect bot"
git remote add origin https://github.com/YOUR_USERNAME/philaconnect.git
git push -u origin main
```

⚠️ Create a `.gitignore` file with just `.env` in it so your secrets aren't exposed:
```
echo ".env" > .gitignore
```

### Step 9 – Deploy to Railway

1. Go to **https://railway.app** → Sign up with GitHub
2. Click **"New Project"** → **"Deploy from GitHub repo"**
3. Select your `philaconnect` repo
4. Railway will auto-detect and deploy it

### Step 10 – Add Environment Variables on Railway

1. Click your deployed project
2. Click **"Variables"** tab
3. Add these one by one:
   - `WHATSAPP_ACCESS_TOKEN` = your token
   - `WHATSAPP_PHONE_NUMBER_ID` = your phone number ID
   - `VERIFY_TOKEN` = `philaconnect_secret_2024`
4. Railway will redeploy automatically

### Step 11 – Get Your Public URL

1. Click **"Settings"** in Railway
2. Under **"Domains"**, click **"Generate Domain"**
3. You'll get a URL like: `https://philaconnect-production.up.railway.app`
4. **Copy this URL** – you'll need it for the webhook

---

## PHASE 3: CONNECT THE WEBHOOK

### Step 12 – Configure Webhook in Meta

1. Go back to **https://developers.facebook.com/apps**
2. Select your PhilaConnect app
3. In the left sidebar, click **"WhatsApp" → "Configuration"**
4. Under **"Webhook"**, click **"Edit"**
5. Fill in:
   - **Callback URL:** `https://your-railway-url.up.railway.app/webhook`
   - **Verify Token:** `philaconnect_secret_2024`
6. Click **"Verify and Save"**
   - ✅ If it says verified, you're connected!
   - ❌ If it fails, check Railway logs to confirm the server is running

### Step 13 – Subscribe to Webhook Events

1. Still on Configuration page
2. Under **"Webhook Fields"**, click **"Manage"**
3. Find **"messages"** and toggle it ON
4. Click **"Done"**

---

## PHASE 4: ADD YOUR REAL PHONE NUMBER

### Step 14 – Add Your WhatsApp Number (0746264454)

1. In Meta Dashboard → **WhatsApp → Phone Numbers**
2. Click **"Add Phone Number"**
3. Enter: **+27 74 626 4454**
4. Verify via OTP (Meta will WhatsApp or call you)
5. Once verified, get your new **Phone Number ID** for this number
6. Update the `WHATSAPP_PHONE_NUMBER_ID` in Railway variables

### Step 15 – Get a Permanent Access Token

Temporary tokens expire. For permanent access:

1. Go to **https://business.facebook.com/settings**
2. Click **"System Users"** → **"Add"**
3. Create a system user named `philaconnect-bot` with Admin role
4. Click **"Add Assets"** → select your WhatsApp app
5. Click **"Generate Token"** → select your app → select permissions:
   - `whatsapp_business_messaging`
   - `whatsapp_business_management`
6. Copy the token and update `WHATSAPP_ACCESS_TOKEN` in Railway

---

## PHASE 5: TEST YOUR BOT

### Step 16 – Test It!

1. Open WhatsApp on your phone
2. Message your WhatsApp Business number
3. Type: **hi**
4. You should see the PhilaConnect menu appear! 🎉

---

## BOT CONVERSATION FLOW

```
User sends: "hi" or "hello" or "menu"
    ↓
Bot shows 3 buttons:
  📅 Book Appointment
  🗂 My Appointments  
  🔄 Reschedule

── BOOKING PATH ──
→ Select Doctor (from list)
→ Select Date (next 7 weekdays)
→ Select Time (08:00 – 16:00)
→ Confirm → ✅ Booking confirmed with reference number

── VIEW PATH ──
→ Shows all your active appointments

── RESCHEDULE PATH ──
→ Select which appointment
→ Select new date
→ Select new time
→ Confirm → ✅ Rescheduled

── CANCEL (from appointment view) ──
→ Select appointment
→ Confirm → ✅ Cancelled
```

---

## TROUBLESHOOTING

| Problem | Solution |
|---------|----------|
| Webhook verification failed | Check Railway logs, confirm server is running, verify token matches |
| Messages not received | Check webhook subscription includes "messages" field |
| Token expired | Generate new token or use permanent system user token |
| Bot not responding | Check Railway logs for errors |

---

## UPGRADING TO A REAL DATABASE

The current code uses in-memory storage (data resets on server restart).
For production, replace `db.js` with MongoDB:

```bash
npm install mongoose
```

Then sign up at **https://mongodb.com/atlas** (free tier) and get your connection string.

---

## COSTS

| Service | Cost |
|---------|------|
| Railway hosting | Free tier (500hrs/month) |
| Meta WhatsApp API | Free for first 1,000 conversations/month |
| MongoDB Atlas | Free tier (512MB) |
| **Total** | **R0/month to start** |

---

## SUPPORT & NEXT STEPS

Once working, you can add:
- SMS reminders before appointments
- Doctor availability calendars
- Payment integration (medical aid)
- Admin dashboard to view all bookings
- Multi-language support (Zulu, Xhosa, Afrikaans)
