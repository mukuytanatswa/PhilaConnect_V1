const axios = require('axios');

const PHONE_NUMBER_ID = process.env.WHATSAPP_PHONE_NUMBER_ID;
const ACCESS_TOKEN = process.env.WHATSAPP_ACCESS_TOKEN;

const BASE_URL = `https://graph.facebook.com/v19.0/${PHONE_NUMBER_ID}/messages`;

const headers = () => ({
  'Authorization': `Bearer ${ACCESS_TOKEN}`,
  'Content-Type': 'application/json',
});

// Send a plain text message
async function sendText(to, text) {
  await axios.post(BASE_URL, {
    messaging_product: 'whatsapp',
    to,
    type: 'text',
    text: { body: text },
  }, { headers: headers() });
}

// Send a list of buttons (max 3 buttons)
async function sendButtons(to, bodyText, buttons) {
  const payload = {
    messaging_product: 'whatsapp',
    to,
    type: 'interactive',
    interactive: {
      type: 'button',
      body: { text: bodyText },
      action: {
        buttons: buttons.map(b => ({
          type: 'reply',
          reply: { id: b.id, title: b.title },
        })),
      },
    },
  };
  await axios.post(BASE_URL, payload, { headers: headers() });
}

// Send a list menu (for more options)
async function sendList(to, bodyText, buttonText, sections) {
  const payload = {
    messaging_product: 'whatsapp',
    to,
    type: 'interactive',
    interactive: {
      type: 'list',
      body: { text: bodyText },
      action: {
        button: buttonText,
        sections,
      },
    },
  };
  await axios.post(BASE_URL, payload, { headers: headers() });
}

module.exports = { sendText, sendButtons, sendList };
