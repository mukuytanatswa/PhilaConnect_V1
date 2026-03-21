require('dotenv').config();
const express = require('express');
const bodyParser = require('body-parser');
const { handleMessage } = require('./bot');

const app = express();
app.use(bodyParser.urlencoded({ extended: false }));
app.use(bodyParser.json());

// WhatsApp webhook verification
app.get('/webhook', (req, res) => {
  const VERIFY_TOKEN = process.env.VERIFY_TOKEN || 'philaconnect_secret_2024';
  const mode = req.query['hub.mode'];
  const token = req.query['hub.verify_token'];
  const challenge = req.query['hub.challenge'];

  if (mode === 'subscribe' && token === VERIFY_TOKEN) {
    console.log('Webhook verified!');
    res.status(200).send(challenge);
  } else {
    res.sendStatus(403);
  }
});

// Incoming WhatsApp messages
app.post('/webhook', async (req, res) => {
  try {
    const body = req.body;

    if (body.object === 'whatsapp_business_account') {
      const entry = body.entry?.[0];
      const changes = entry?.changes?.[0];
      const value = changes?.value;
      const messages = value?.messages;

      if (messages && messages.length > 0) {
        const message = messages[0];
        const from = message.from; // sender phone number
        const msgType = message.type;

        let userText = '';
        if (msgType === 'text') {
          userText = message.text.body;
        } else if (msgType === 'interactive') {
          userText = message.interactive?.button_reply?.id ||
                     message.interactive?.list_reply?.id || '';
        }

        console.log(`Message from ${from}: ${userText}`);
        await handleMessage(from, userText);
      }
    }

    res.sendStatus(200);
  } catch (err) {
    console.error('Webhook error:', err);
    res.sendStatus(200); // Always return 200 to WhatsApp
  }
});

app.get('/', (req, res) => res.send('PhilaConnect Bot is running!'));

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => console.log(`PhilaConnect running on port ${PORT}`));
