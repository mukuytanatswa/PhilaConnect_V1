# PhilaConnect: Appointment Rescheduling & Flow Analysis

## 📋 Executive Summary

Found **3 critical issues**:
1. **Old appointments NOT cancelled during reschedule** - Direct SQL UPDATE without cancelling
2. **Trigger words only work at idle state** - Users trapped in booking/reschedule flows
3. **8 states allow users to get stuck** - No escape routes from selection states

---

## 1. APPOINTMENT RESCHEDULING FLOW

### 1.1 send_reschedule_options() Function
**Location:** [logic.py](logic.py#L344-L351)

```python
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
```

✅ **What it does:** Lists user's appointments and transitions to `select_reschedule` state.

---

### 1.2 select_reschedule State Handler
**Location:** [logic.py](logic.py#L174-L182)

```python
elif state == "select_reschedule":
    try:
        appointment_id = int(text)
        appointments = get_appointments(phone=phone)
        if 1 <= appointment_id <= len(appointments):
            data['reschedule_id'] = appointments[appointment_id-1][0]
            data['doctor_id'] = appointments[appointment_id-1][1]
            set_state(phone, "reschedule_date", data)
            send_dates(phone, data['doctor_id'])
```

✅ **What it does:** 
- Extracts appointment ID to reschedule
- Stores it in `data['reschedule_id']` for later update
- Transitions to `reschedule_date` state

---

### 1.3 reschedule_time State Handler - THE PROBLEM
**Location:** [logic.py](logic.py#L207-L221)

```python
elif state == "reschedule_time":
    try:
        time_index = int(text)
        times = get_available_times(data['doctor_id'], data['new_date'])
        if 1 <= time_index <= len(times):
            data['new_time'] = times[time_index-1]
            # Update appointment
            conn = sqlite3.connect('philaconnect.db')
            c = conn.cursor()
            c.execute('UPDATE appointments SET date = ?, time = ? WHERE id = ?', 
                     (data['new_date'], data['new_time'], data['reschedule_id']))
            conn.commit()
            conn.close()
            set_state(phone, None, {})
            send_message(phone, f"APPOINTMENT RESCHEDULED\n\nNew Date: {data['new_date']}\nNew Time: {data['new_time']}")
```

### ⚠️ **CRITICAL ISSUE: Old Appointment NOT Cancelled**

**Problem:** The code does a direct `UPDATE` on the appointment record. The old appointment is simply updated to the new time/date.

**What SHOULD happen:**
- Old appointment should be marked as `cancelled` or `rescheduled`
- A NEW appointment record should be created with the new date/time
- User should see history of their reschedule action

**What's ACTUALLY happening:**
- Only ONE appointment record exists (the updated one)
- No audit trail
- Can't track when appointment was rescheduled
- Violates appointment history best practices

**Database impact:** 
- Loss of appointment history
- No record of what the original appointment was
- No tracking of when/why rescheduling occurred

---

## 2. TRIGGER WORD HANDLING - USERS GET STUCK

### 2.1 Current Implementation
**Location:** [logic.py](logic.py#L47-L50)

```python
# Show menu for greetings or explicit requests
greetings = ["hi", "hello", "hey", "menu", "start", "help"]
if text.lower() in greetings:
    send_menu(phone)
    return
```

### ⚠️ **CRITICAL ISSUE: Only Checked at Start**

This check happens **BEFORE** state-specific handlers and **ONLY triggers when returning to menu**. 

**The control flow is:**
```
1. Extract message
2. ✅ Check trigger words (ONLY HERE!)
3. Check main menu options (1, 2, 3, 4) - only if state is None/idle
4. State-specific handlers (select_doctor, select_date, etc.)
5. Else: ignore
```

### ⚠️ **States Where Trigger Words Are IGNORED:**

| State | Can User Escape? | Trigger Words Work? |
|-------|---|---|
| `select_hospital` | ❌ No escape | ❌ NO |
| `select_doctor` | ❌ No escape | ❌ NO |
| `select_date` | ❌ No escape* | ❌ NO |
| `select_time` | ❌ No escape | ❌ NO |
| `select_cancel` | ❌ No escape | ❌ NO |
| `select_reschedule` | ❌ No escape | ❌ NO |
| `reschedule_date` | ❌ No escape | ❌ NO |
| `reschedule_time` | ❌ No escape | ❌ NO |
| `update_user_info` | ✅ Has escape (option 3) | ❌ NO |
| `update_name` | ❌ No escape | ❌ NO |
| `update_phone` | ❌ No escape | ❌ NO |

*`select_date` has "MORE" option but that's pagination, not escape

### 2.2 Example User Getting Stuck

**Scenario:** User selecting a doctor but changes mind
```
User: hi
Bot: Shows menu
User: 1 (to book appointment)
Bot: Shows hospitals
User: 1 (selects hospital)
Bot: Shows doctors
User: hi (TRIES to get back to menu)
Bot: IGNORES "hi" and says "Please reply with doctor number"
User: STUCK - no way out except by selecting a doctor
```

---

## 3. STATES WITHOUT EXIT ROUTES

### List of Problematic States:

1. **`select_hospital`** [Lines 71-87]
   - No "back" option
   - No trigger word escape
   - Invalid input just re-prompts

2. **`select_doctor`** [Lines 89-128]
   - No "back" option
   - No trigger word escape
   - Can type doctor name but no explicit exit

3. **`select_date`** [Lines 130-151]
   - Has "MORE" for pagination only
   - No "back" or escape
   - No trigger word escape

4. **`select_time`** [Lines 153-168]
   - No "back" or escape
   - No trigger word escape
   - Only accepts numbers 1-N

5. **`select_cancel`** [Lines 170-181]
   - No "back" option
   - No trigger word escape
   - Must select a number

6. **`select_reschedule`** [Lines 183-192]
   - No "back" option  
   - No trigger word escape
   - Must select a number

7. **`reschedule_date`** [Lines 194-204]
   - No "back" option (inherits from select_date)
   - No trigger word escape
   - Has "MORE" for pagination only

8. **`update_user_info`** [Lines 223-232]
   - ✅ HAS escape: option "3" goes back to menu
   - ❌ Still ignores trigger words

**States with partial escape:**
- `update_name` → Auto-complete, sets state to None (OK)
- `update_phone` → Any +27 input auto-completes (OK)

---

## 4. RECOMMENDATIONS

### Priority 1: FIX RESCHEDULING

**Instead of:**
```python
c.execute('UPDATE appointments SET date = ?, time = ? WHERE id = ?', 
         (data['new_date'], data['new_time'], data['reschedule_id']))
```

**Do this:**
```python
# 1. Mark old appointment as rescheduled
c.execute('UPDATE appointments SET status = ? WHERE id = ?', 
         ('rescheduled', data['reschedule_id']))

# 2. Create new appointment record
c.execute('INSERT INTO appointments (phone, doctor_id, date, time, status, created_at) VALUES (?, ?, ?, ?, ?, ?)',
         (phone, data['doctor_id'], data['new_date'], data['new_time'], 'confirmed', datetime.now()))
```

### Priority 2: CHECK TRIGGER WORDS IN ALL STATES

**Move trigger word check AFTER extracting message but check in a loop:**

```python
# After getting state and data
state, data = get_state(phone)

# ✅ Check trigger words REGARDLESS of state
if text.lower() in ["hi", "hello", "hey", "menu", "start", "help"]:
    send_menu(phone)
    return

# Then proceed with other handlers...
```

### Priority 3: ADD ESCAPE ROUTES

Add "0" or "BACK" option to all selection states:

```python
def send_doctors(phone, hospital_id, context=None):
    # ... existing code ...
    msg = "DOCTOR LIST (choose by number):\n\n"
    for i, (id, name, specialty, available_days) in enumerate(doctors, 1):
        msg += f"{i}. {name} | {specialty} | Days: {available_days}\n"
    msg += "\n0️⃣ Back to menu"  # ADD THIS
    msg += "\nReply with the doctor number (e.g., 1)."
    send_message(phone, msg)
```

Then in handler:
```python
elif state == "select_doctor":
    if text == "0":  # ADD THIS
        send_menu(phone)
        return
    # ... rest of handler ...
```

---

## Summary Table

| Issue | Severity | Impact | Lines |
|-------|----------|--------|-------|
| Old appointment not cancelled on reschedule | 🔴 CRITICAL | Data loss, no audit trail | 213-219 |
| Trigger words only work at idle | 🔴 CRITICAL | Users get stuck mid-flow | 47-50 |
| No escape from 8 states | 🟡 HIGH | Poor UX, user frustration | Multiple |

