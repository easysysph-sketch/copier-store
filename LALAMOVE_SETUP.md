# CopierStore — Lalamove API Setup

This version adds a **server-side Lalamove v3 quotation integration**. It does not put your API secret in the browser.

## 1. Create Lalamove API credentials

Use Lalamove's Developer/Partner Portal and create **Sandbox** credentials first. Production credentials require the production wallet/credits.

Official docs: https://developers.lalamove.com/

## 2. Set environment variables

Windows CMD:

```bat
set LALAMOVE_API_KEY=pk_test_your_key
set LALAMOVE_API_SECRET=sk_test_your_secret
set LALAMOVE_ENV=sandbox
set LALAMOVE_MARKET=PH
set LALAMOVE_SERVICE_TYPE=MOTORCYCLE
set LALAMOVE_PICKUP_NAME=CopierStore
set LALAMOVE_PICKUP_PHONE=+63XXXXXXXXXX
set LALAMOVE_PICKUP_ADDRESS=YOUR EXACT COPIERSTORE ADDRESS
set STORE_LATITUDE=YOUR_STORE_LATITUDE
set STORE_LONGITUDE=YOUR_STORE_LONGITUDE
python app.py
```

PowerShell:

```powershell
$env:LALAMOVE_API_KEY='pk_test_your_key'
$env:LALAMOVE_API_SECRET='sk_test_your_secret'
$env:LALAMOVE_ENV='sandbox'
$env:LALAMOVE_MARKET='PH'
$env:LALAMOVE_SERVICE_TYPE='MOTORCYCLE'
$env:LALAMOVE_PICKUP_NAME='CopierStore'
$env:LALAMOVE_PICKUP_PHONE='+63XXXXXXXXXX'
$env:LALAMOVE_PICKUP_ADDRESS='YOUR EXACT COPIERSTORE ADDRESS'
$env:STORE_LATITUDE='YOUR_STORE_LATITUDE'
$env:STORE_LONGITUDE='YOUR_STORE_LONGITUDE'
python app.py
```

## 3. How checkout works

Customer selects a saved address with an exact GPS pin → chooses **Lalamove** → CopierStore's Flask backend requests a live quotation from Lalamove → checkout displays the returned PHP price.

The browser never receives `LALAMOVE_API_SECRET`.

## 4. Important

- Do not commit API keys/secrets to GitHub.
- Sandbox is for testing. Production requires production credentials and wallet credits.
- The quote is time-limited by Lalamove, so the server requests a fresh quote again when the order is submitted.
- The existing Standard Delivery calculation remains available as a fallback.
- J&T is intentionally **not faked** as an API integration. Add J&T credentials/API only when an official merchant/API contract is available.

## If the checkout says the API is not configured

The app now automatically loads `copier_store/.env` when it starts. Copy `.env.example` to `.env`, enter your credentials, then restart Flask. No `python-dotenv` package is required.


## Product shipping specifications

Each product stores packed **weight (kg)** and **dimensions (L × W × H in cm)**. Checkout aggregates these values for bulky-order review and optional courier capacity checks. Lalamove's current API documentation says the structured `item.weight`/category information is only supported in Thailand, Vietnam, and Hong Kong, so the Philippines integration does not send unsupported raw dimensions as Lalamove `item` fields.
