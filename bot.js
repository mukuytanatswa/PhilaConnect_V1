const { sendText, sendButtons, sendList } = require('./whatsapp');
const {
  DOCTORS, TIME_SLOTS,
  getSession, setSession, clearSession,
  createAppointment, getAppointmentsByPhone,
  getAppointmentById, cancelAppointment,
  rescheduleAppointment, getDoctorById,
  formatAppointment, getAvailableDates,
} = require('./db');

// ─── MAIN ROUTER ────────────────────────────────────────────────────────────
async function handleMessage(from, text) {
  const session = getSession(from);
  const input = text.trim().toLowerCase();

  // Global escape commands
  if (['menu', 'hi', 'hello', 'start', 'hola', 'hey'].includes(input)) {
    clearSession(from);
    return sendMainMenu(from);
  }
  if (input === 'cancel' && session.state !== 'IDLE') {
    clearSession(from);
    return sendText(from, '❌ Action cancelled. Type *menu* to start again.');
  }

  switch (session.state) {
    case 'IDLE':
      return handleIdle(from, input);

    // BOOKING FLOW
    case 'BOOK_SELECT_DOCTOR':
      return handleBookSelectDoctor(from, input, session);
    case 'BOOK_SELECT_DATE':
      return handleBookSelectDate(from, input, session);
    case 'BOOK_SELECT_TIME':
      return handleBookSelectTime(from, input, session);
    case 'BOOK_CONFIRM':
      return handleBookConfirm(from, input, session);

    // CANCEL FLOW
    case 'CANCEL_SELECT':
      return handleCancelSelect(from, input, session);
    case 'CANCEL_CONFIRM':
      return handleCancelConfirm(from, input, session);

    // RESCHEDULE FLOW
    case 'RESCHEDULE_SELECT':
      return handleRescheduleSelect(from, input, session);
    case 'RESCHEDULE_DATE':
      return handleRescheduleDate(from, input, session);
    case 'RESCHEDULE_TIME':
      return handleRescheduleTime(from, input, session);
    case 'RESCHEDULE_CONFIRM':
      return handleRescheduleConfirm(from, input, session);

    default:
      clearSession(from);
      return sendMainMenu(from);
  }
}

// ─── MAIN MENU ───────────────────────────────────────────────────────────────
async function sendMainMenu(from) {
  await sendButtons(
    from,
    `👋 Welcome to *PhilaConnect* – Your Health Appointment Assistant!\n\nWhat would you like to do?`,
    [
      { id: 'book',        title: '📅 Book Appointment' },
      { id: 'manage',      title: '🗂 My Appointments' },
      { id: 'reschedule',  title: '🔄 Reschedule' },
    ]
  );
}

async function handleIdle(from, input) {
  if (input === 'book')       return startBooking(from);
  if (input === 'manage')     return showAppointments(from);
  if (input === 'reschedule') return startReschedule(from);
  if (input === 'cancel_appt') return startCancel(from);
  return sendMainMenu(from);
}

// ─── BOOKING FLOW ─────────────────────────────────────────────────────────
async function startBooking(from) {
  const sections = [{
    title: 'Available Doctors',
    rows: DOCTORS.map(d => ({
      id: `doc_${d.id}`,
      title: d.name,
      description: d.specialty,
    })),
  }];
  setSession(from, 'BOOK_SELECT_DOCTOR', {});
  await sendList(from, '👨‍⚕️ Please select a doctor:', 'Choose Doctor', sections);
}

async function handleBookSelectDoctor(from, input, session) {
  const doctorId = input.replace('doc_', '');
  const doctor = getDoctorById(doctorId);
  if (!doctor) return sendText(from, '⚠️ Invalid selection. Please choose from the list.');

  const dates = getAvailableDates();
  setSession(from, 'BOOK_SELECT_DATE', { doctorId });

  await sendList(
    from,
    `✅ You selected *${doctor.name}*.\n\n📅 Scroll and choose an appointment date:`,
    'View Dates',
    buildDateSections(dates, 'date')
  );
}

async function handleBookSelectDate(from, input, session) {
  const date = input.replace('date_', '');
  if (!date.match(/^\d{4}-\d{2}-\d{2}$/)) {
    return sendText(from, '⚠️ Please select a date from the list.');
  }

  setSession(from, 'BOOK_SELECT_TIME', { ...session.data, date });

  await sendList(
    from,
    `📅 Date: *${formatDateTitle(date)}*\n\n🕐 Scroll and pick a time slot:`,
    'View Times',
    buildTimeSections('time')
  );
}

async function handleBookSelectTime(from, input, session) {
  const time = input.replace('time_', '');
  if (!TIME_SLOTS.includes(time)) {
    return sendText(from, '⚠️ Please select a time from the list.');
  }

  const { doctorId, date } = session.data;
  const doctor = getDoctorById(doctorId);
  setSession(from, 'BOOK_CONFIRM', { doctorId, date, time });

  await sendButtons(
    from,
    `🔍 *Please confirm your appointment:*\n\n👨‍⚕️ Doctor: ${doctor.name}\n🏥 Specialty: ${doctor.specialty}\n📅 Date: ${formatDateTitle(date)}\n🕐 Time: ${formatTime(time)}\n\nConfirm booking?`,
    [
      { id: 'confirm_book', title: '✅ Confirm' },
      { id: 'cancel',       title: '❌ Cancel' },
    ]
  );
}

async function handleBookConfirm(from, input, session) {
  if (input === 'cancel') {
    clearSession(from);
    return sendMainMenu(from);
  }
  if (input !== 'confirm_book') {
    return sendText(from, 'Please tap ✅ Confirm or ❌ Cancel.');
  }

  const { doctorId, date, time } = session.data;
  const appt = createAppointment(from, doctorId, date, time);
  const doctor = getDoctorById(doctorId);

  clearSession(from);
  await sendText(
    from,
    `🎉 *Appointment Booked Successfully!*\n\n${formatAppointment(appt)}\n\n📌 Save your reference number: *${appt.id}*\n\nType *menu* to return to the main menu.`
  );
}

// ─── VIEW APPOINTMENTS ────────────────────────────────────────────────────
async function showAppointments(from) {
  const appts = getAppointmentsByPhone(from);

  if (appts.length === 0) {
    await sendButtons(
      from,
      `📋 You have no upcoming appointments.\n\nWould you like to book one?`,
      [
        { id: 'book',   title: '📅 Book Now' },
        { id: 'cancel', title: '❌ Back' },
      ]
    );
    return;
  }

  const list = appts.map(a => formatAppointment(a)).join('\n\n─────────────\n\n');
  await sendText(from, `📋 *Your Appointments:*\n\n${list}\n\nType *menu* to go back.`);
}

// ─── CANCEL FLOW ────────────────────────────────────────────────────────────
async function startCancel(from) {
  const appts = getAppointmentsByPhone(from);
  if (appts.length === 0) {
    return sendText(from, '📋 You have no appointments to cancel.\n\nType *menu* to go back.');
  }

  const sections = [{
    title: 'Your Appointments',
    rows: appts.map(a => {
      const doc = getDoctorById(a.doctorId);
      return {
        id: `cancel_${a.id}`,
        title: `${a.id} – ${a.date}`,
        description: `${doc?.name} at ${a.time}`,
      };
    }),
  }];

  setSession(from, 'CANCEL_SELECT', {});
  await sendList(from, '❌ Which appointment would you like to cancel?', 'Select Appointment', sections);
}

async function handleCancelSelect(from, input, session) {
  const apptId = input.replace('cancel_', '');
  const appt = getAppointmentById(apptId);
  if (!appt || appt.patientPhone !== from) {
    return sendText(from, '⚠️ Appointment not found. Type *menu* to go back.');
  }

  setSession(from, 'CANCEL_CONFIRM', { apptId });
  const doctor = getDoctorById(appt.doctorId);

  await sendButtons(
    from,
    `⚠️ Are you sure you want to cancel this appointment?\n\n${formatAppointment(appt)}\n\nThis cannot be undone.`,
    [
      { id: 'confirm_cancel', title: '✅ Yes, Cancel' },
      { id: 'no_cancel',      title: '↩️ Keep It' },
    ]
  );
}

async function handleCancelConfirm(from, input, session) {
  if (input !== 'confirm_cancel') {
    clearSession(from);
    return sendMainMenu(from);
  }

  cancelAppointment(session.data.apptId);
  clearSession(from);
  await sendText(from, `✅ Appointment *${session.data.apptId}* has been cancelled.\n\nType *menu* to go back to the main menu.`);
}

// ─── RESCHEDULE FLOW ─────────────────────────────────────────────────────────
async function startReschedule(from) {
  const appts = getAppointmentsByPhone(from);
  if (appts.length === 0) {
    return sendText(from, '📋 You have no appointments to reschedule.\n\nType *menu* to go back.');
  }

  const sections = [{
    title: 'Your Appointments',
    rows: appts.map(a => {
      const doc = getDoctorById(a.doctorId);
      return {
        id: `rsch_${a.id}`,
        title: `${a.id} – ${a.date}`,
        description: `${doc?.name} at ${a.time}`,
      };
    }),
  }];

  setSession(from, 'RESCHEDULE_SELECT', {});
  await sendList(from, '🔄 Which appointment would you like to reschedule?', 'Select Appointment', sections);
}

async function handleRescheduleSelect(from, input, session) {
  const apptId = input.replace('rsch_', '');
  const appt = getAppointmentById(apptId);
  if (!appt || appt.patientPhone !== from) {
    return sendText(from, '⚠️ Appointment not found.');
  }

  const dates = getAvailableDates();
  setSession(from, 'RESCHEDULE_DATE', { apptId });

  await sendList(
    from,
    `📅 Select a new date for appointment *${apptId}*:`,
    'View Dates',
    buildDateSections(dates, 'ndate')
  );
}

async function handleRescheduleDate(from, input, session) {
  const date = input.replace('ndate_', '');
  setSession(from, 'RESCHEDULE_TIME', { ...session.data, newDate: date });

  await sendList(
    from,
    `📅 New date: *${formatDateTitle(date)}*\n\n🕐 Scroll and pick a new time:`,
    'View Times',
    buildTimeSections('ntime')
  );
}

async function handleRescheduleTime(from, input, session) {
  const time = input.replace('ntime_', '');
  const { apptId, newDate } = session.data;
  const appt = getAppointmentById(apptId);
  const doctor = getDoctorById(appt.doctorId);

  setSession(from, 'RESCHEDULE_CONFIRM', { apptId, newDate, newTime: time });

  await sendButtons(
    from,
    `🔍 *Confirm Reschedule:*\n\n📋 Ref: ${apptId}\n👨‍⚕️ Doctor: ${doctor.name}\n📅 New Date: ${formatDateTitle(newDate)}\n🕐 New Time: ${formatTime(time)}`,
    [
      { id: 'confirm_reschedule', title: '✅ Confirm' },
      { id: 'cancel',             title: '❌ Cancel' },
    ]
  );
}

async function handleRescheduleConfirm(from, input, session) {
  if (input !== 'confirm_reschedule') {
    clearSession(from);
    return sendMainMenu(from);
  }

  const { apptId, newDate, newTime } = session.data;
  const updated = rescheduleAppointment(apptId, newDate, newTime);
  clearSession(from);

  await sendText(
    from,
    `✅ *Appointment Rescheduled!*\n\n${formatAppointment(updated)}\n\nType *menu* to go back.`
  );
}

// ─── DATE / TIME FORMATTING HELPERS ─────────────────────────────────────────

function formatDateTitle(dateStr) {
  const [year, month, day] = dateStr.split('-').map(Number);
  const d = new Date(year, month - 1, day);
  return d.toLocaleDateString('en-ZA', { weekday: 'short', day: 'numeric', month: 'short' });
}

function formatDateDescription(dateStr) {
  const [year, month, day] = dateStr.split('-').map(Number);
  const date = new Date(year, month - 1, day);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const diffDays = Math.round((date - today) / (1000 * 60 * 60 * 24));

  if (diffDays === 1) return 'Tomorrow';
  if (diffDays <= 6) return `This ${date.toLocaleDateString('en-ZA', { weekday: 'long' })}`;
  return date.toLocaleDateString('en-ZA', { day: 'numeric', month: 'long', year: 'numeric' });
}

function buildDateSections(dates, prefix = 'date') {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const dayOfWeek = today.getDay();
  const daysToNextMonday = dayOfWeek === 0 ? 1 : 8 - dayOfWeek;
  const nextMonday = new Date(today);
  nextMonday.setDate(today.getDate() + daysToNextMonday);
  const followingMonday = new Date(nextMonday);
  followingMonday.setDate(nextMonday.getDate() + 7);

  const thisWeek = [], nextWeek = [], later = [];

  for (const dateStr of dates) {
    const [y, m, d] = dateStr.split('-').map(Number);
    const date = new Date(y, m - 1, d);
    if (date < nextMonday) thisWeek.push(dateStr);
    else if (date < followingMonday) nextWeek.push(dateStr);
    else later.push(dateStr);
  }

  const sections = [];
  if (thisWeek.length > 0) {
    sections.push({
      title: 'This Week',
      rows: thisWeek.map(d => ({
        id: `${prefix}_${d}`,
        title: formatDateTitle(d),
        description: formatDateDescription(d),
      })),
    });
  }
  if (nextWeek.length > 0) {
    sections.push({
      title: 'Next Week',
      rows: nextWeek.map(d => ({
        id: `${prefix}_${d}`,
        title: formatDateTitle(d),
        description: formatDateDescription(d),
      })),
    });
  }
  if (later.length > 0) {
    sections.push({
      title: 'Upcoming',
      rows: later.map(d => ({
        id: `${prefix}_${d}`,
        title: formatDateTitle(d),
        description: formatDateDescription(d),
      })),
    });
  }
  return sections;
}

function formatTime(timeStr) {
  const [h, m] = timeStr.split(':').map(Number);
  const period = h < 12 ? 'AM' : 'PM';
  const hour12 = h === 0 ? 12 : h > 12 ? h - 12 : h;
  return `${hour12}:${m.toString().padStart(2, '0')} ${period}`;
}

function buildTimeSections(prefix = 'time') {
  const morning = TIME_SLOTS.filter(t => parseInt(t.split(':')[0]) < 12);
  const afternoon = TIME_SLOTS.filter(t => parseInt(t.split(':')[0]) >= 12);
  const sections = [];
  if (morning.length > 0) {
    sections.push({
      title: 'Morning ☀️',
      rows: morning.map(t => ({
        id: `${prefix}_${t}`,
        title: formatTime(t),
        description: 'Available',
      })),
    });
  }
  if (afternoon.length > 0) {
    sections.push({
      title: 'Afternoon 🌤️',
      rows: afternoon.map(t => ({
        id: `${prefix}_${t}`,
        title: formatTime(t),
        description: 'Available',
      })),
    });
  }
  return sections;
}

module.exports = { handleMessage };
