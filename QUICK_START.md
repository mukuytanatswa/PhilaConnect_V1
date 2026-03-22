# PhilaConnect - Quick Start & Testing Guide

## System Overview

The PhilaConnect health bot now has a complete appointment management system with:
- Dashboard for clinic staff
- WhatsApp bot for patients  
- Automated reminders
- Appointment cancellation/rescheduling with notifications

---

## Running the Application

### Starting the Bot

```bash
# Terminal 1: Start the FastAPI server (main.py uses this for dashboard + webhooks)
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

```bash
# Terminal 2 (Optional): If using Node.js bot (bot.js + index.js)
npm install
node index.js
```

---

## Dashboard Access

- **URL**: `http://localhost:8000/dashboard`
- **Default Hospital**: The Riverside Cottage
- **Initial Doctors**: 3 sample doctors (Dr. Kotzé-Scott, Dr. Awe, Dr. Blumenthal)

---

## Dashboard Features

### 1. Dashboard View (Default)
- **Stats**: Shows actual counts of today's appointments, active doctors
- **Upcoming Today**: List of next 5 appointments with action buttons
- **Doctor Status**: Toggle doctors on/off, see appointment load per doctor
- **WhatsApp Notifications**: Shows notification logs (empty until reminders are sent)

### 2. Appointments View
- **Filter by Doctor**: Use dropdown to filter appointments
- **Add Appointment**: "+ Add" button opens form
- **View Details**: 👁 button shows appointment details modal
- **Reschedule**: ↺ button opens reschedule form
- **Cancel**: ✕ button opens cancel form with message option

### 3. Doctors View
- **Doctor Management**: Add new doctors or modify existing ones
- **Toggle Status**: Turn doctors on/off for availability
- **Availability Days**: Click day pills to set working days
- **Appointment Count**: See how many appointments per doctor today

### 4. Reminders View
- **Schedule Timeline**: Visual explanation of when reminders are sent
- **Message Previews**: See examples of each reminder message
- **Reminder Stats**: Delivery rate, reschedule rate, no-show reduction %

---

## Bot Commands (WhatsApp)

### Main Menu
Send: `menu` or `start`
```
Welcome to PhilaConnect 👋

Reply with:
1️⃣ Book appointment
2️⃣ Reschedule appointment
3️⃣ Cancel appointment
4️⃣ Update my information
```

### Book Appointment
1. Send `1` → Select doctor
2. Send doctor number → Select date
3. Send date number → Select time
4. Send time number → Review and confirm
5. Get confirmation with appointment ID

### Reschedule Appointment
1. Send `2` → Select appointment to reschedule
2. Pick new date → Pick new time
3. Confirm → Receive updated appointment details

### Cancel Appointment
1. Send `3` → Select appointment to cancel
2. Confirm cancellation → Get confirmation

### Update User Information
1. Send `4` → Choose what to update
2. Send `1` → Update name (just type your new name)
3. Send `2` → Update phone (format: +27XXXXXXXXX)
4. Send `3` → Return to menu

---

## Testing Scenarios

### Test 1: Complete Appointment Flow
1. User sends "menu"
2. User sends "1" to book
3. Follow steps to select doctor, date, time
4. Verify appointment appears in dashboard
5. Verify appointment detail modal shows correct doctor

### Test 2: Doctor Filtering
1. Open Appointments view in dashboard
2. Select a specific doctor from dropdown
3. Verify only that doctor's appointments show
4. Select "All Doctors" → All appointments return

### Test 3: Cancel Appointment
1. From dashboard, click ✕ on an appointment
2. Add cancel message (e.g., "Emergency maintenance")
3. Click "Cancel & Notify"
4. Verify patient receives WhatsApp: ❌ Your appointment has been cancelled. Reason: Emergency maintenance...

### Test 4: Reschedule Appointment
1. From dashboard, click ↺ on an appointment
2. Select new date and time
3. Add reschedule message (e.g., "Doctor running behind schedule")
4. Click "Save & Notify"
5. Verify patient receives: 📅 Your appointment has been rescheduled!

### Test 5: User Profile
1. Patient sends "4" in bot
2. Responds "1" and types name "John Doe"
3. Database stores name linked to phone number
4. Next time, bot can reference "John Doe" in future features

### Test 6: Appointment Detail Modal
1. In dashboard Appointments view, click 👁 on any appointment
2. Verify modal shows:
   - Correct patient phone
   - Correct doctor name and specialty
   - Correct date and time
   - Correct hospital name
   - Status (Confirmed)

### Test 7: Reminders (Manual Testing)
The system checks for reminders every 5 minutes. To test:
1. Create appointment scheduled for ~48 hours from now
2. Wait for reminder window (47-49 hours before)
3. Create appointment for tomorrow morning
4. System will send reminder at ~7 AM
5. Create appointment for 1 hour from now
6. Wait for reminder window (0.8-1.2 hours before)

**Faster Testing**: Modify appointment dates/times in database directly to trigger reminders sooner

---

## Appointment Data in Dashboard

Each appointment shows:
- **Time**: Appointment time (e.g., 08:00)
- **Patient**: Patient phone number, initials in avatar
- **Doctor**: Doctor's name
- **Type**: Appointment type (default: General)
- **Status**: Confirmed, Pending, or Cancelled
- **Reminder**: Reminder status (Pending, Sent, etc.)
- **Actions**: View detail, Reschedule, Cancel buttons

---

## Key Database Tables

### appointments
```sql
id | phone | doctor_id | date | time | status | created_at
```

### appointments (with doctor_id join)
Returns: id, doctor_id, phone, doctor_name, hospital, date, time, status

### user_profiles
```sql
phone | name | preferred_hospital_id | created_at | updated_at
```

### user_states
```sql
phone | state | data (JSON)
```

### doctors
```sql
id | name | specialty | hospital_id | is_active | available_days
```

---

## API Endpoints

### Dashboard
- `GET /dashboard` - Main dashboard page
- `POST /add_appointment` - Create new appointment
- `POST /add_doctor` - Add new doctor
- `POST /toggle_doctor` - Enable/disable doctor

### Appointments
- `GET /api/appointment/{id}` - Get appointment details (returns JSON)
- `POST /cancel_appointment` - Cancel appointment + send notification
- `POST /reschedule_appointment` - Reschedule + send notification

### Doctor Management
- `POST /toggle_doctor` - Toggle doctor active/inactive
- `POST /update_doctor_availability` - Set available days

### Webhooks
- `GET /webhook` - WhatsApp verification
- `POST /webhook` - Receive WhatsApp messages

---

## Troubleshooting

### Reminders Not Sending
1. Check scheduler is running: "Reminder scheduler started" in logs
2. Verify appointment times are in future
3. Check WhatsApp token in whatsapp.py is valid
4. Look for errors in console output

### Appointments Not Showing in Dashboard
1. Verify database file exists: `philaconnect.db`
2. Check appointments have status = 'booked'
3. Try refreshing dashboard page
4. Check browser console for JavaScript errors

### Modal Showing Wrong Doctor
1. Check database appointments table has correct doctor_id
2. Verify doctors table has correct data
3. Try refreshing page
4. Check /api/appointment/{id} endpoint is returning correct data

### Patient Not Receiving Messages
1. Check WhatsApp token and Phone ID in whatsapp.py
2. Verify patient phone format is correct (+27XXXXXXXXX)
3. Check WhatsApp Business account is active
4. Look for API errors in console

---

## Next Steps for Integration

1. **Doctor App**: When doctor app is ready, integrate doctor login
2. **Analytics**: Enable Reports section when doctor app is live
3. **History**: Add appointment history/archive views
4. **Payments**: Integrate payment processing if needed
5. **SMS**: Add SMS fallback for reminders
6. **Custom Messages**: Allow doctors to customize reminder templates

---

## Important Notes

- ⚠️ **Never** commit API tokens to version control
- 🔒 Keep WhatsApp token secure in whatsapp.py
- 📊 Reminders send via WhatsApp Business API - ensure account is verified
- 💾 Database is SQLite (philaconnect.db) - back it up regularly
- 🚀 For production, use:
  - Gunicorn instead of uvicorn
  - PostgreSQL instead of SQLite
  - Proper error logging
  - Environment variables for secrets

