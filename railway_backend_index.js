const express = require("express");
const cors = require("cors");
const crypto = require("crypto");

const app = express();
const PORT = process.env.PORT || 3000;

app.use(cors());
app.use(express.json());

app.get("/", (req, res) => {
  res.json({ status: "ok", message: "WOMPI Backend Running" });
});

app.post("/create-payment", async (req, res) => {
  try {
    const {
      amount_in_cents,
      currency,
      customer_email,
      payment_method,
      reference,
      customer_data,
      redirect_url,
      financial_institution_code,
      user_type,
      user_legal_id_type,
      user_legal_id,
      payment_description
    } = req.body;

    console.log("Received payment request:", JSON.stringify(req.body, null, 2));

    const WOMPI_PUBLIC_KEY = process.env.WOMPI_PUBLIC_KEY;
    const WOMPI_PRIVATE_KEY = process.env.WOMPI_PRIVATE_KEY;
    const WOMPI_INTEGRITY_SECRET = process.env.WOMPI_INTEGRITY_SECRET;

    if (!WOMPI_PUBLIC_KEY || !WOMPI_PRIVATE_KEY || !WOMPI_INTEGRITY_SECRET) {
      console.error("Missing WOMPI environment variables");
      return res.status(500).json({
        success: false,
        error: "Server configuration error - missing WOMPI credentials"
      });
    }

    const finalReference = reference || "RUNETIC-" + Date.now();
    const integrityString = finalReference + amount_in_cents + currency + WOMPI_INTEGRITY_SECRET;
    const integritySignature = crypto.createHash("sha256").update(integrityString).digest("hex");

    console.log("Generated integrity signature for reference:", finalReference);

    const acceptanceResponse = await fetch("https://api.wompi.co/v1/merchants/" + WOMPI_PUBLIC_KEY, {
      method: "GET",
      headers: { "Content-Type": "application/json" }
    });

    const acceptanceData = await acceptanceResponse.json();
    const acceptanceToken = acceptanceData.data.presigned_acceptance.acceptance_token;

    console.log("Got acceptance token");

    let transactionBody = {
      amount_in_cents: amount_in_cents,
      currency: currency,
      customer_email: customer_email,
      reference: finalReference,
      signature: integritySignature,
      acceptance_token: acceptanceToken,
      payment_method: {
        type: payment_method.type,
        installments: payment_method.installments || 1
      },
      customer_data: customer_data,
      redirect_url: redirect_url
    };

    if (payment_method.type === "PSE") {
      transactionBody.payment_method = {
        type: "PSE",
        user_type: user_type === "natural" ? 0 : 1,
        user_legal_id_type: user_legal_id_type || "CC",
        user_legal_id: user_legal_id,
        financial_institution_code: financial_institution_code,
        payment_description: payment_description || "Compra RUNETIC"
      };
    }

    if (payment_method.type === "CARD" && payment_method.token) {
      transactionBody.payment_method.token = payment_method.token;
    }

    console.log("Creating transaction with body:", JSON.stringify(transactionBody, null, 2));

    const transactionResponse = await fetch("https://api.wompi.co/v1/transactions", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + WOMPI_PRIVATE_KEY
      },
      body: JSON.stringify(transactionBody)
    });

    const transactionData = await transactionResponse.json();
    console.log("Transaction response:", JSON.stringify(transactionData, null, 2));

    if (transactionData.error) {
      return res.status(400).json({
        success: false,
        error: transactionData.error.reason || transactionData.error.type || "Transaction failed"
      });
    }

    const transactionId = transactionData.data.id;

    await new Promise(resolve => setTimeout(resolve, 1500));

    const checkResponse = await fetch("https://api.wompi.co/v1/transactions/" + transactionId, {
      method: "GET",
      headers: {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + WOMPI_PRIVATE_KEY
      }
    });

    const checkData = await checkResponse.json();
    console.log("Transaction check response:", JSON.stringify(checkData, null, 2));

    let checkoutUrl = null;

    if (checkData.data && checkData.data.payment_method && checkData.data.payment_method.extra) {
      checkoutUrl = checkData.data.payment_method.extra.async_payment_url;
    }

    if (!checkoutUrl && payment_method.type === "PSE") {
      checkoutUrl = "https://checkout.wompi.co/l/" + transactionId;
    }

    return res.json({
      success: true,
      transaction_id: transactionId,
      checkout_url: checkoutUrl,
      reference: finalReference,
      status: checkData.data ? checkData.data.status : transactionData.data.status
    });

  } catch (error) {
    console.error("Payment error:", error);
    return res.status(500).json({
      success: false,
      error: error.message || "Internal server error"
    });
  }
});

app.listen(PORT, () => {
  console.log("WOMPI Backend running on port " + PORT);
});
