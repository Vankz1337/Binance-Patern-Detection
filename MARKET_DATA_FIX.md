# Invictus Web 2.0 Alpha 5 - market data fix

Observed failure: TLS certificate hostname mismatch when the Windows environment connected to Binance market-data hostnames.

Fix:
- Primary public market-data endpoint: https://data-api.binance.vision
- Secondary: https://api-gcp.binance.com
- Official API fallbacks: api.binance.com, api1.binance.com, api2.binance.com
- Frontend direct fallback uses the same endpoint order.

Do not disable TLS certificate verification.

