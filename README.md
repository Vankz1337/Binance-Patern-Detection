# Invictus Web 2.0 Alpha 20

Single-web trading workspace with separate dashboards:

- **Dashboard** — detailed coin chart, pattern lifecycle, MTF flow, technical summary.
- **Pattern Finder** — select a pattern, configure timeframe/sensitivity/universe, then scan Binance USDT spot markets.
- **Live Scanner** — current active pattern states from the watch universe.

## Run

Terminal 1:

```bat
cd backend
.venv\Scripts\activate
uvicorn app.main:app --reload --port 8000
```

Terminal 2:

```bat
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173/`.

