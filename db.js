// Simple in-memory store (replace with a real DB like MongoDB/PostgreSQL in production)
// Data structure:
//   appointments[appointmentId] = { id, patientPhone, doctorId, date, time, status }
//   sessions[phoneNumber] = { state, data }

const appointments = {};
const sessions = {};
let appointmentCounter = 1000;

// --- DOCTORS ---
const DOCTORS = [
  { id: 'dr_mokoena', name: 'Dr. Mokoena', specialty: 'General Practitioner' },
  { id: 'dr_naidoo',  name: 'Dr. Naidoo',  specialty: 'Cardiologist' },
  { id: 'dr_smith',   name: 'Dr. Smith',   specialty: 'Dermatologist' },
  { id: 'dr_dlamini', name: 'Dr. Dlamini', specialty: 'Paediatrician' },
];

// Available time slots
const TIME_SLOTS = ['08:00', '09:00', '10:00', '11:00', '14:00', '15:00', '16:00'];

// --- SESSION MANAGEMENT ---
function getSession(phone) {
  if (!sessions[phone]) sessions[phone] = { state: 'IDLE', data: {} };
  return sessions[phone];
}

function setSession(phone, state, data = {}) {
  sessions[phone] = { state, data };
}

function clearSession(phone) {
  sessions[phone] = { state: 'IDLE', data: {} };
}

// --- APPOINTMENT MANAGEMENT ---
function createAppointment(patientPhone, doctorId, date, time) {
  const id = `PHILA${++appointmentCounter}`;
  appointments[id] = {
    id,
    patientPhone,
    doctorId,
    date,
    time,
    status: 'confirmed',
    createdAt: new Date().toISOString(),
  };
  return appointments[id];
}

function getAppointmentsByPhone(phone) {
  return Object.values(appointments).filter(
    a => a.patientPhone === phone && a.status !== 'cancelled'
  );
}

function getAppointmentById(id) {
  return appointments[id] || null;
}

function cancelAppointment(id) {
  if (appointments[id]) {
    appointments[id].status = 'cancelled';
    return true;
  }
  return false;
}

function rescheduleAppointment(id, newDate, newTime) {
  if (appointments[id]) {
    appointments[id].date = newDate;
    appointments[id].time = newTime;
    appointments[id].status = 'rescheduled';
    return appointments[id];
  }
  return null;
}

function getDoctorById(id) {
  return DOCTORS.find(d => d.id === id) || null;
}

function formatAppointment(appt) {
  const doctor = getDoctorById(appt.doctorId);
  return `📋 *Ref:* ${appt.id}\n👨‍⚕️ *Doctor:* ${doctor ? doctor.name : appt.doctorId}\n📅 *Date:* ${appt.date}\n🕐 *Time:* ${appt.time}\n✅ *Status:* ${appt.status}`;
}

// Generate next 7 available weekday dates
function getAvailableDates() {
  const dates = [];
  const d = new Date();
  while (dates.length < 7) {
    d.setDate(d.getDate() + 1);
    const day = d.getDay();
    if (day !== 0 && day !== 6) { // skip weekends
      dates.push(d.toISOString().split('T')[0]);
    }
  }
  return dates;
}

module.exports = {
  DOCTORS, TIME_SLOTS,
  getSession, setSession, clearSession,
  createAppointment, getAppointmentsByPhone,
  getAppointmentById, cancelAppointment,
  rescheduleAppointment, getDoctorById,
  formatAppointment, getAvailableDates,
};
