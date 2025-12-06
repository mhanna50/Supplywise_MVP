# SupplyWise MVP

SupplyWise is a lightweight supplier risk scoring tool that combines Azure Maps, GLEIF, and OpenAI data to produce a simple, explainable risk indicator.

## Backend (Django + DRF)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate  # or use your preferred env manager
pip install -r requirements.txt
cp ../.env.example .env  # fill in keys for Azure, GLEIF, and OpenAI
python manage.py migrate
python manage.py runserver 8000
```

The backend exposes three endpoints:
- `GET /api/suppliers/search/` - proxies Azure Maps fuzzy search for business-only results.
- `POST /api/suppliers/assess/` - runs GLEIF enrichment, heuristic risk scoring, and OpenAI explanation.
- `POST /api/suppliers/deep-risk/` - fans out to SEC EDGAR, OSHA, FEMA, and EPA ECHO to assemble deep-risk panels.

Environment variables used:
- `AZURE_MAPS_SUBSCRIPTION_KEY`, `AZURE_MAPS_BASE_URL`, `AZURE_MAPS_SEARCH_API_VERSION`
- `GLEIF_BASE_URL`
- `OPENAI_API_KEY`, `OPENAI_MODEL`
- Public data feeds:
  - `SEC_API_USER_AGENT`, `SEC_API_CONTACT_EMAIL`, optionally `SEC_COMPANY_SEARCH_URL`, `SEC_COMPANY_FACTS_URL`
  - `OSHA_API_BASE_URL`
  - `FEMA_API_BASE_URL`
  - `EPA_ECHO_BASE_URL`
- Standard Django values like `DJANGO_SECRET_KEY`/`DJANGO_DEBUG`

## Frontend (React + Vite)

```bash
cd frontend
npm install
npm run dev
```

The Vite dev server listens on `http://localhost:5173` by default and talks to the Django API at `http://localhost:8000`.

The React client auto-detects the backend when it is running via `npm run dev` on port 5173 (or the preview server on 4173). If you host the API elsewhere, copy `frontend/.env.example` to `frontend/.env` and set `VITE_SUPPLIERS_API_ORIGIN` to the backend origin (for example, `https://api.example.com`). The client will append `/api/suppliers` automatically and continue to proxy all search traffic through the Django endpoint before it hits Azure Maps' fuzzy search API.

## Using the app

1. Start both servers.
2. Open the frontend in your browser.
3. Search for a supplier (optionally add city/state/country filters).
4. Click **Assess Risk** on a result to fetch GLEIF data, compute a score, and generate an AI explanation.
5. Review the rich card plus collapsible debug panels that reveal raw Azure, GLEIF, and internal risk payloads.

> **Note:** Provide real keys for Azure Maps, GLEIF, and OpenAI in your `.env`. The `.env.example` file documents all required values.
