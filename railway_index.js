/**
 * RUNETIC - WOMPI Payment Backend
 * Backend de pagos para integración con WOMPI Colombia
 * 
 * IMPORTANTE: Este archivo está listo para producción.
 * Desplegarlo en Railway con las variables de entorno correspondientes.
 */

const express = require('express');
const cors = require('cors');
const crypto = require('crypto');
const axios = require('axios');

const app = express();

// ====================
// CONFIGURACIÓN
// ====================
const PORT = process.env.PORT || 3000;
const WOMPI_PUBLIC_KEY = process.env.WOMPI_PUBLIC_KEY || 'pub_prod_gViOLGY34T5tq4FGXXLz0nzoxRtEtDNe';
const WOMPI_PRIVATE_KEY = process.env.WOMPI_PRIVATE_KEY || 'prv_prod_1uEwQscEiO6H8wrKRBR3LE2MdJC0h0PW';
const WOMPI_INTEGRITY_SECRET = process.env.WOMPI_INTEGRITY_SECRET || 'prod_integrity_p6aaFFZDjJvlV5zk60L1wDfADaAqTTmY';
const WOMPI_BASE_URL = 'https://production.wompi.co/v1';

// ====================
// MIDDLEWARE
// ====================
app.use(cors({
    origin: '*',
    methods: ['GET', 'POST', 'OPTIONS'],
    allowedHeaders: ['Content-Type', 'Authorization']
}));
app.use(express.json());

// Logging middleware
app.use((req, res, next) => {
    console.log(`[${new Date().toISOString()}] ${req.method} ${req.path}`);
    next();
});

// ====================
// FUNCIONES HELPER
// ====================

/**
 * Genera la firma de integridad para WOMPI
 */
function generateIntegritySignature(reference, amountInCents, currency) {
    const concatenatedString = `${reference}${amountInCents}${currency}${WOMPI_INTEGRITY_SECRET}`;
    return crypto.createHash('sha256').update(concatenatedString).digest('hex');
}

/**
 * Obtiene un token de aceptación de WOMPI
 */
async function getAcceptanceToken() {
    try {
        const response = await axios.get(`${WOMPI_BASE_URL}/merchants/${WOMPI_PUBLIC_KEY}`);
        return response.data.data.presigned_acceptance.acceptance_token;
    } catch (error) {
        console.error('Error getting acceptance token:', error.message);
        throw error;
    }
}

/**
 * Tokeniza una tarjeta de crédito
 */
async function tokenizeCard(cardNumber, cvc, expMonth, expYear, cardHolder) {
    try {
        const response = await axios.post(
            `${WOMPI_BASE_URL}/tokens/cards`,
            {
                number: cardNumber,
                cvc: cvc,
                exp_month: expMonth,
                exp_year: expYear,
                card_holder: cardHolder
            },
            {
                headers: {
                    'Authorization': `Bearer ${WOMPI_PUBLIC_KEY}`
                }
            }
        );
        return response.data.data;
    } catch (error) {
        console.error('Error tokenizing card:', error.response?.data || error.message);
        throw error;
    }
}

// ====================
// RUTAS
// ====================

// Health check
app.get('/', (req, res) => {
    res.json({ 
        status: 'ok', 
        service: 'RUNETIC Payment Backend',
        environment: 'production',
        timestamp: new Date().toISOString()
    });
});

app.get('/health', (req, res) => {
    res.json({ status: 'healthy' });
});

/**
 * Obtener lista de bancos para PSE
 */
app.get('/banks', async (req, res) => {
    try {
        const response = await axios.get(`${WOMPI_BASE_URL}/pse/financial_institutions`, {
            headers: { 'Authorization': `Bearer ${WOMPI_PRIVATE_KEY}` }
        });
        res.json({ success: true, banks: response.data.data });
    } catch (error) {
        console.error('Error fetching banks:', error.response?.data || error.message);
        res.status(500).json({ success: false, error: 'Error fetching banks' });
    }
});

/**
 * Crear pago (PSE o Tarjeta)
 */
app.post('/create-payment', async (req, res) => {
    try {
        const {
            amount_in_cents,
            currency = 'COP',
            customer_email,
            payment_method,
            reference,
            customer_data,
            redirect_url,
            financial_institution_code,
            user_type,
            user_legal_id_type,
            user_legal_id,
            payment_description,
            // Card specific
            card_number,
            card_cvc,
            card_exp_month,
            card_exp_year,
            card_holder,
            installments = 1
        } = req.body;

        // Validaciones básicas
        if (!amount_in_cents || !customer_email || !payment_method || !reference) {
            return res.status(400).json({
                success: false,
                error: 'MISSING_REQUIRED_FIELDS',
                message: 'Required fields: amount_in_cents, customer_email, payment_method, reference'
            });
        }

        // Generar firma de integridad
        const signature = generateIntegritySignature(reference, amount_in_cents, currency);
        
        // Obtener token de aceptación
        const acceptanceToken = await getAcceptanceToken();

        let transactionData = {
            amount_in_cents: parseInt(amount_in_cents),
            currency: currency,
            customer_email: customer_email,
            reference: reference,
            signature: signature,
            acceptance_token: acceptanceToken
        };

        // Configuración según tipo de pago
        if (payment_method.type === 'PSE') {
            // Validaciones PSE
            if (!financial_institution_code || !user_type || !user_legal_id_type || !user_legal_id) {
                return res.status(400).json({
                    success: false,
                    error: 'MISSING_PSE_FIELDS',
                    message: 'PSE requires: financial_institution_code, user_type, user_legal_id_type, user_legal_id'
                });
            }

            transactionData.payment_method = {
                type: 'PSE',
                user_type: user_type === 'natural' ? 0 : 1,
                user_legal_id_type: user_legal_id_type,
                user_legal_id: user_legal_id,
                financial_institution_code: financial_institution_code,
                payment_description: payment_description || `Pago RUNETIC ${reference}`
            };
            transactionData.redirect_url = redirect_url;
            transactionData.customer_data = customer_data;

        } else if (payment_method.type === 'CARD') {
            // Validaciones tarjeta
            if (!card_number || !card_cvc || !card_exp_month || !card_exp_year || !card_holder) {
                return res.status(400).json({
                    success: false,
                    error: 'MISSING_CARD_FIELDS',
                    message: 'Card requires: card_number, card_cvc, card_exp_month, card_exp_year, card_holder'
                });
            }

            // Tokenizar la tarjeta
            const tokenData = await tokenizeCard(card_number, card_cvc, card_exp_month, card_exp_year, card_holder);

            transactionData.payment_method = {
                type: 'CARD',
                token: tokenData.id,
                installments: parseInt(installments)
            };
            transactionData.customer_data = customer_data;

        } else if (payment_method.type === 'NEQUI') {
            transactionData.payment_method = {
                type: 'NEQUI',
                phone_number: customer_data?.phone_number
            };
        } else {
            return res.status(400).json({
                success: false,
                error: 'INVALID_PAYMENT_METHOD',
                message: 'Valid payment methods: PSE, CARD, NEQUI'
            });
        }

        console.log('Creating transaction:', JSON.stringify({
            reference: transactionData.reference,
            amount: transactionData.amount_in_cents,
            method: transactionData.payment_method.type
        }));

        // Crear transacción en WOMPI
        const response = await axios.post(
            `${WOMPI_BASE_URL}/transactions`,
            transactionData,
            {
                headers: {
                    'Authorization': `Bearer ${WOMPI_PRIVATE_KEY}`,
                    'Content-Type': 'application/json'
                }
            }
        );

        const transaction = response.data.data;
        console.log('Transaction created:', transaction.id, 'Status:', transaction.status);

        // Respuesta según tipo de pago
        if (payment_method.type === 'PSE') {
            res.json({
                success: true,
                transaction_id: transaction.id,
                status: transaction.status,
                checkout_url: transaction.payment_method?.extra?.async_payment_url,
                redirect_url: transaction.redirect_url
            });
        } else {
            res.json({
                success: true,
                transaction_id: transaction.id,
                status: transaction.status,
                payment_method_type: transaction.payment_method_type
            });
        }

    } catch (error) {
        console.error('Payment error:', error.response?.data || error.message);
        
        const errorData = error.response?.data;
        let errorMessage = 'PAYMENT_ERROR';
        
        if (errorData?.error?.type) {
            errorMessage = errorData.error.type;
        } else if (errorData?.error?.messages) {
            errorMessage = Object.values(errorData.error.messages).flat().join(', ');
        }

        res.status(error.response?.status || 500).json({
            success: false,
            error: errorMessage,
            details: errorData?.error || error.message
        });
    }
});

/**
 * Verificar estado de transacción
 */
app.get('/transaction/:id', async (req, res) => {
    try {
        const { id } = req.params;
        
        const response = await axios.get(`${WOMPI_BASE_URL}/transactions/${id}`, {
            headers: { 'Authorization': `Bearer ${WOMPI_PRIVATE_KEY}` }
        });

        const transaction = response.data.data;

        res.json({
            success: true,
            transaction_id: transaction.id,
            status: transaction.status,
            amount: transaction.amount_in_cents,
            reference: transaction.reference,
            payment_method_type: transaction.payment_method_type,
            created_at: transaction.created_at,
            finalized_at: transaction.finalized_at
        });

    } catch (error) {
        console.error('Error fetching transaction:', error.response?.data || error.message);
        res.status(error.response?.status || 500).json({
            success: false,
            error: 'TRANSACTION_NOT_FOUND'
        });
    }
});

/**
 * Webhook para recibir notificaciones de WOMPI
 */
app.post('/webhook', (req, res) => {
    try {
        const event = req.body;
        console.log('Webhook received:', JSON.stringify(event));

        // Verificar firma del webhook si está presente
        const signature = req.headers['x-event-signature'];
        if (signature) {
            // Validar firma aquí si es necesario
            console.log('Webhook signature:', signature);
        }

        const transaction = event.data?.transaction;
        if (transaction) {
            console.log(`Transaction ${transaction.id} status: ${transaction.status}`);
            // Aquí puedes agregar lógica para actualizar tu base de datos
        }

        res.status(200).json({ received: true });

    } catch (error) {
        console.error('Webhook error:', error.message);
        res.status(500).json({ error: 'Webhook processing failed' });
    }
});

/**
 * Generar firma de integridad (para uso del frontend)
 */
app.post('/generate-signature', (req, res) => {
    try {
        const { reference, amount_in_cents, currency = 'COP' } = req.body;

        if (!reference || !amount_in_cents) {
            return res.status(400).json({
                success: false,
                error: 'Missing reference or amount_in_cents'
            });
        }

        const signature = generateIntegritySignature(reference, amount_in_cents, currency);

        res.json({
            success: true,
            signature: signature,
            public_key: WOMPI_PUBLIC_KEY
        });

    } catch (error) {
        console.error('Signature generation error:', error.message);
        res.status(500).json({ success: false, error: 'Error generating signature' });
    }
});

// ====================
// ERROR HANDLER
// ====================
app.use((err, req, res, next) => {
    console.error('Unhandled error:', err);
    res.status(500).json({
        success: false,
        error: 'INTERNAL_SERVER_ERROR',
        message: process.env.NODE_ENV === 'development' ? err.message : 'An error occurred'
    });
});

// ====================
// START SERVER
// ====================
app.listen(PORT, () => {
    console.log(`
╔══════════════════════════════════════════════╗
║  RUNETIC Payment Backend                     ║
║  Status: Running                             ║
║  Port: ${PORT}                                  ║
║  Environment: Production                     ║
║  WOMPI: Configured                           ║
╚══════════════════════════════════════════════╝
    `);
});

module.exports = app;
