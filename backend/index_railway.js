require('dotenv').config();

const express = require('express');
const axios = require('axios');
const crypto = require('crypto');
const cors = require('cors');

const app = express();
app.use(cors());
app.use(express.json());

const WOMPI_PUBLIC_KEY = process.env.WOMPI_PUBLIC_KEY;
const WOMPI_PRIVATE_KEY = process.env.WOMPI_PRIVATE_KEY;
const WOMPI_INTEGRITY_SECRET = process.env.WOMPI_INTEGRITY_SECRET;
const PORT = process.env.PORT;

if (!WOMPI_PUBLIC_KEY || !WOMPI_PRIVATE_KEY || !WOMPI_INTEGRITY_SECRET) {
  console.error('Faltan variables de entorno de WOMPI');
  process.exit(1);
}

const WOMPI_API = 'https://production.wompi.co/v1';

app.get('/', function(req, res) {
  res.send('Backend WOMPI activo');
});

app.post('/create-payment', async function(req, res) {
  try {
    var amount = req.body.amount;
    var reference = req.body.reference;
    var email = req.body.email;
    var financial_institution_code = req.body.financial_institution_code;
    var user_type = req.body.user_type;
    var user_legal_id_type = req.body.user_legal_id_type;
    var user_legal_id = req.body.user_legal_id;
    var payment_description = req.body.payment_description;
    var full_name = req.body.full_name;
    var phone_number = req.body.phone_number;

    if (!amount || !reference || !email || !financial_institution_code || user_type === undefined || !user_legal_id_type || !user_legal_id) {
      return res.status(400).json({ error: 'Datos incompletos' });
    }

    var amountInCents = Math.round(amount * 100);

    var signature = crypto.createHash('sha256')
      .update(reference + amountInCents + 'COP' + WOMPI_INTEGRITY_SECRET)
      .digest('hex');

    var merchantRes = await axios.get(WOMPI_API + '/merchants/' + WOMPI_PUBLIC_KEY);
    var acceptanceToken = merchantRes.data.data.presigned_acceptance.acceptance_token;

    var wompiResponse = await axios.post(WOMPI_API + '/transactions', {
      amount_in_cents: amountInCents,
      currency: 'COP',
      signature: signature,
      customer_email: email,
      reference: reference,
      acceptance_token: acceptanceToken,
      payment_method: {
        type: 'PSE',
        financial_institution_code: financial_institution_code,
        user_type: parseInt(user_type),
        user_legal_id_type: user_legal_id_type,
        user_legal_id: user_legal_id,
        payment_description: payment_description || 'Pago ' + reference
      },
      customer_data: {
        full_name: full_name || 'Cliente',
        phone_number: phone_number || '3000000000',
        legal_id: user_legal_id,
        legal_id_type: user_legal_id_type
      }
    }, {
      headers: {
        'Authorization': 'Bearer ' + WOMPI_PRIVATE_KEY,
        'Content-Type': 'application/json'
      }
    });

    var txData = wompiResponse.data.data;
    var transactionId = txData.id;

    await new Promise(function(resolve) { setTimeout(resolve, 1000); });

    var txQuery = await axios.get(WOMPI_API + '/transactions/' + transactionId);
    var txFull = txQuery.data.data;

    var checkoutUrl = txFull.redirect_url;
    if (!checkoutUrl && txFull.payment_method && txFull.payment_method.extra) {
      checkoutUrl = txFull.payment_method.extra.async_payment_url || txFull.payment_method.extra.pseURL;
    }

    console.log('Transaction ID:', transactionId);
    console.log('Checkout URL:', checkoutUrl);

    res.json({
      success: true,
      checkout_url: checkoutUrl,
      transaction_id: transactionId,
      status: txFull.status
    });

  } catch (error) {
    console.error('Error WOMPI:', error.response ? error.response.data : error.message);
    res.status(500).json({ error: 'Error creando el pago', details: error.response ? error.response.data : error.message });
  }
});

app.post('/webhook', function(req, res) {
  console.log('Webhook:', JSON.stringify(req.body, null, 2));
  res.status(200).send('ok');
});

var serverPort = PORT || 3000;
app.listen(serverPort, function() {
  console.log('Servidor WOMPI en puerto ' + serverPort);
});
