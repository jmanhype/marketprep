# MarketPrep

Inventory recommendation system for farmers market vendors. Pulls sales data from Square POS, combines it with weather forecasts and local event listings, and outputs per-product quantity suggestions for upcoming markets.

**Status:** Prototype. Backend API exists, frontend renders, Docker Compose starts all services. Not yet validated with real vendor data. No paying users.

## What It Does

1. Connects to a vendor's Square POS account via OAuth 2.0.
2. Imports product catalog and historical sales.
3. Fetches weather forecasts (OpenWeatherMap) and nearby events (Eventbrite).
4. Runs a RandomForest model (scikit-learn, ~30 features) to predict per-product demand.
5. Returns quantity recommendations through a REST API consumed by a React PWA.
6. Accepts post-market feedback to retrain the model.

If weather or event API keys are missing, the system falls back to historical averages. The model has not been benchmarked against real market data.

## Architecture

```
React PWA (Vite + TS) --> FastAPI (Python 3.11) --> PostgreSQL 15 (RLS)
                                |
                                +---> Redis 7 (cache)
                                +---> Celery (async tasks)
                                +---> Square API (sales data)
                                +---> OpenWeatherMap API
                                +---> Eventbrite API
```

## Tech Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| Backend | FastAPI, Python 3.11 | JWT auth, bcrypt passwords |
| Database | PostgreSQL 15 | Row-level security for multi-tenancy |
| Cache | Redis 7 | Session and query caching |
| ML | scikit-learn RandomForest | ~30 features, no production benchmark yet |
| Frontend | React 18, TypeScript, Vite | Tailwind CSS, PWA-capable |
| Infra | Docker Compose | Multi-stage builds |
| CI | GitHub Actions | Lint, test, build |
| Migrations | Alembic | 6 migration files |

## Running Locally

Requires Docker and Docker Compose.

```bash
git clone https://github.com/jmanhype/marketprep.git
cd marketprep
docker-compose up -d
```

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API docs (Swagger): http://localhost:8000/api/docs

First build takes ~5 minutes. Subsequent starts take ~30 seconds.

### Environment Variables

Copy `.env.example` to `.env`. Required for production:

| Variable | Purpose | Required |
|----------|---------|----------|
| `SECRET_KEY` | JWT signing (32+ chars) | Yes |
| `ENCRYPTION_KEY` | OAuth token encryption (32 bytes) | Yes |
| `SQUARE_APPLICATION_ID` | Square POS integration | No (disables POS sync) |
| `SQUARE_APPLICATION_SECRET` | Square POS integration | No |
| `OPENWEATHER_API_KEY` | Weather forecasts | No (falls back to averages) |
| `EVENTBRITE_API_KEY` | Local event detection | No (falls back to manual entry) |

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/auth/register` | POST | Create vendor account |
| `/api/v1/auth/login` | POST | Get JWT tokens |
| `/api/v1/vendors/me` | GET | Current vendor profile |
| `/api/v1/products` | GET | Product catalog |
| `/api/v1/recommendations` | POST | Generate quantity predictions |
| `/api/v1/sales` | GET | Sales history |
| `/health` | GET | Health check |
| `/metrics` | GET | Prometheus metrics |

## Tests

The test suite claims 1,230 passing tests and 100% backend coverage. These numbers come from the project's CI output and have not been independently verified. E2E tests use screenshot-based validation.

```bash
# Backend
cd backend && pytest --cov=src

# Frontend build check
cd frontend && npm run build
```

## Code Size

| Component | Lines |
|-----------|-------|
| Backend (Python) | ~5,200 |
| Frontend (TypeScript) | ~3,500 |
| Alembic migrations | 6 files |
| Test files | Not counted separately |

## Limitations

- No real vendor data has been run through the system. Accuracy claims are untested.
- The RandomForest model ships with no pre-trained weights; it requires sufficient sales history before producing useful predictions.
- Subscription tiers (Free/Professional/Enterprise) are defined in the README but billing is not implemented.
- The PWA offline mode caches the shell but cannot generate recommendations offline.
- Rate limiting is configured (100/min anonymous, 1,000/min authenticated) but has not been load-tested in production.
- GDPR compliance features (data export, deletion) are partially implemented.

## Project History

Built as a prototype using Claude Code and the Spec Kit framework. Development took approximately 2 weeks covering 204 tasks. No external contributors at this time.

## License

MIT. See [LICENSE](LICENSE).
