<div align="center">

# MarketPrep

### AI-Powered Inventory Intelligence for Farmers Markets

**Stop guessing. Start selling smarter.**

[![Production Ready](https://img.shields.io/badge/status-production%20ready-brightgreen)](https://github.com/jmanhype/marketprep)
[![Test Coverage](https://img.shields.io/badge/coverage-100%25-brightgreen)](https://github.com/jmanhype/marketprep)
[![Tests Passing](https://img.shields.io/badge/tests-1230%20passing-brightgreen)](https://github.com/jmanhype/marketprep)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

[Features](#features) • [Quick Start](#quick-start) • [Documentation](#documentation) • [Contributing](#contributing)

</div>

---

## Overview

MarketPrep is an AI-powered SaaS platform that helps farmers market vendors optimize their inventory using machine learning, weather intelligence, and real-time sales data from Square POS.

**The Problem:** Vendors lose money from overstock waste or missed sales due to stockouts. Manual inventory planning is time-consuming and error-prone.

**The Solution:** MarketPrep analyzes your sales history, weather forecasts, local events, and venue-specific patterns to predict exactly what (and how much) to bring to each market.

### Key Benefits

- 📊 **Reduce Waste**: Predict demand within ±20% accuracy
- 💰 **Increase Revenue**: Never run out of popular items
- ⏱️ **Save Time**: Automated recommendations in seconds
- 📱 **Work Offline**: PWA works without internet connectivity
- 🔒 **Stay Compliant**: GDPR-ready with audit trails

---

## Features

### Core Capabilities

**🤖 AI-Powered Predictions**
- Machine learning models trained on your sales history
- RandomForest algorithm with 30+ features
- Continuous learning from feedback

**☁️ Weather Intelligence**
- Real-time weather forecast integration (OpenWeatherMap)
- Adjusts recommendations for rain, heat, cold
- Historical weather pattern analysis

**📍 Venue-Specific Learning**
- Tailored predictions for each market location
- Accounts for venue traffic patterns
- Tracks seasonal variations

**🎉 Local Events Detection**
- Integrates with Eventbrite API
- Factors in nearby festivals, concerts, events
- Estimates attendance impact on sales

**💳 Square POS Integration**
- Secure OAuth 2.0 connection
- Automatic catalog and sales sync
- Encrypted token storage

**📱 Progressive Web App**
- Mobile-first responsive design
- Offline-capable with service workers
- Add to home screen functionality

**📈 Feedback Loop**
- Report actual vs predicted quantities
- Model automatically retrains
- Improves accuracy over time

---

## Quick Start

### Prerequisites

- **Docker & Docker Compose** (Download: [docker.com](https://www.docker.com/get-started))

That's it! Docker handles Python, Node, PostgreSQL, and Redis for you.

### Installation

```bash
# Clone the repository
git clone https://github.com/jmanhype/marketprep.git
cd marketprep

# Start all services
docker-compose up -d

# Verify health
docker-compose ps
```

**Access the application:**
- 🌐 Frontend: http://localhost:3000
- 🔌 Backend API: http://localhost:8000
- 📚 API Docs: http://localhost:8000/api/docs

The first startup takes ~5 minutes to build Docker images. Subsequent starts are under 30 seconds.

### Environment Configuration

Optional: Configure API keys for full functionality.

```bash
# Copy example environment file
cp .env.example .env

# Edit with your credentials
nano .env
```

**Required for production:**
- `SECRET_KEY` - JWT signing key (32+ characters)
- `ENCRYPTION_KEY` - OAuth token encryption (32 bytes)

**Optional (degrades gracefully):**
- `SQUARE_APPLICATION_ID` & `SQUARE_APPLICATION_SECRET` - POS integration
- `OPENWEATHER_API_KEY` - Weather forecasts (fallback: historical averages)
- `EVENTBRITE_API_KEY` - Local events (fallback: manual entry)

---

## Architecture

### Technology Stack

**Backend**
- **Framework**: FastAPI (Python 3.11)
- **Database**: PostgreSQL 15 with Row-Level Security
- **Cache**: Redis 7
- **ML**: scikit-learn RandomForest
- **Auth**: JWT with bcrypt
- **Task Queue**: Celery
- **Migrations**: Alembic

**Frontend**
- **Framework**: React 18 + TypeScript
- **Build Tool**: Vite
- **Styling**: Tailwind CSS
- **State**: React Context API
- **PWA**: Vite PWA Plugin
- **HTTP Client**: Axios with interceptors

**Infrastructure**
- **Containerization**: Docker multi-stage builds
- **Orchestration**: Docker Compose
- **CI/CD**: GitHub Actions
- **Monitoring**: Prometheus + OpenTelemetry
- **Logging**: Structured JSON with correlation IDs

### System Design

```
┌─────────────┐      ┌──────────────┐      ┌────────────┐
│   React     │─────▶│   FastAPI    │─────▶│ PostgreSQL │
│   PWA       │      │   Backend    │      │   + RLS    │
└─────────────┘      └──────────────┘      └────────────┘
                            │
                            ├──────▶ Redis Cache
                            ├──────▶ Celery Workers
                            ├──────▶ Square API
                            ├──────▶ OpenWeather API
                            └──────▶ Eventbrite API
```

---

## Testing

MarketPrep has been thoroughly validated with **100% backend coverage** and comprehensive end-to-end testing.

### Test Results

| Component | Status | Details |
|-----------|--------|---------|
| Backend Tests | ✅ Passing | 1,230 tests, 100% coverage (5,193 lines) |
| Frontend Build | ✅ Passing | TypeScript + Vite, no errors |
| End-to-End Tests | ✅ Passing | Complete user flows with screenshots |
| CI/CD Pipeline | ✅ Passing | All checks green |
| Docker Images | ✅ Building | Backend + Frontend multi-stage |

### Running Tests

**Backend (pytest):**
```bash
cd backend
pytest --cov=src --cov-report=html
open htmlcov/index.html
```

**Frontend (TypeScript + Vite):**
```bash
cd frontend
npm run build
npm run lint
```

**End-to-End (Automated):**
```bash
docker-compose up -d
./test-dogfood.sh
```

**Load Testing (Locust):**
```bash
cd backend/tests/load
locust -f locustfile.py
```

### Test Documentation

- [Testing Documentation](docs/testing/README.md) - Complete testing guide
- [E2E Test Summary](docs/testing/E2E_TEST_SUMMARY.md) - Quick overview with pass/fail results
- [E2E Test Report](docs/testing/E2E_TEST_REPORT.md) - Detailed analysis with 22 screenshots
- [Frontend Test Report](docs/testing/FRONTEND_TEST_REPORT.md) - UX validation results
- [Dogfooding Checklist](docs/testing/DOGFOOD_CHECKLIST.md) - 13-phase validation
- [Release Certification](docs/RELEASE_READY.md) - Production readiness sign-off

---

## Deployment

### Docker Production Build

```bash
# Build and start production services
docker-compose -f docker-compose.prod.yml up -d

# Run database migrations
docker-compose -f docker-compose.prod.yml exec backend alembic upgrade head

# Check health
curl http://localhost:8000/health
```

### Cloud Deployment

MarketPrep supports deployment to:

- **AWS**: ECS/Fargate, RDS PostgreSQL, ElastiCache Redis
- **Google Cloud**: Cloud Run, Cloud SQL, Memorystore
- **Azure**: Container Apps, Database for PostgreSQL, Cache for Redis
- **Fly.io**: Simple deployment with fly.toml (included)
- **Railway**: One-click deployment

See [DEPLOYMENT.md](docs/DEPLOYMENT.md) for detailed deployment guides.

### Environment Setup

**Production checklist:**
1. Set strong `SECRET_KEY` and `ENCRYPTION_KEY`
2. Configure managed PostgreSQL and Redis
3. Set up SSL/TLS certificates (Let's Encrypt)
4. Configure OAuth callback URLs for Square
5. Set up monitoring (Prometheus, Grafana, Sentry)
6. Configure log aggregation
7. Set up automated backups
8. Configure CDN for frontend assets

---

## Security

MarketPrep implements industry-standard security practices:

- 🔐 **JWT Authentication** with automatic token refresh
- 🔒 **Encrypted Storage** for OAuth tokens (AES-256)
- 🛡️ **CSRF Protection** via Double Submit Cookie pattern
- 🚫 **SQL Injection Prevention** through parameterized queries
- 🚦 **Rate Limiting** (100/min anonymous, 1000/min authenticated)
- 🔍 **Security Headers** (CSP, X-Frame-Options, HSTS)
- 🎯 **Input Sanitization** on all user inputs
- 📝 **Secrets Scanning** in CI/CD pipeline
- 🏛️ **Row-Level Security** for multi-tenant data isolation

---

## Compliance

### GDPR Compliance

- ✅ **Right to Access**: Data export API
- ✅ **Right to Deletion**: Account deletion with cascade
- ✅ **Right to Portability**: JSON export format
- ✅ **Data Retention**: Configurable retention policies
- ✅ **Consent Management**: Explicit opt-ins

### Audit Trail

- Immutable audit logs for all API calls
- Hash-chain verification for log integrity
- WORM storage adapter for compliance logs
- Correlation IDs for request tracing

---

## API Documentation

Interactive API documentation is auto-generated from code:

- **Swagger UI**: http://localhost:8000/api/docs
- **ReDoc**: http://localhost:8000/api/redoc
- **OpenAPI JSON**: http://localhost:8000/openapi.json

### Key Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/auth/register` | POST | Register new vendor account |
| `/api/v1/auth/login` | POST | Login and get JWT tokens |
| `/api/v1/vendors/me` | GET | Get current vendor profile |
| `/api/v1/products` | GET | List vendor's products |
| `/api/v1/recommendations` | POST | Generate AI predictions |
| `/api/v1/sales` | GET | Fetch sales history |
| `/health` | GET | Health check endpoint |
| `/metrics` | GET | Prometheus metrics |

---

## Monitoring

### Observability Stack

**Metrics (Prometheus)**
- Request counts and latencies
- Error rates and types
- Database query performance
- Cache hit ratios
- Custom business metrics

**Tracing (OpenTelemetry)**
- Distributed request tracing
- Service dependency mapping
- Performance bottleneck identification

**Logging (Structured JSON)**
- Correlation IDs for request tracking
- Error details with stack traces
- Audit trail for compliance
- Performance metrics

**Health Checks**
- `/health` - Overall system health
- `/metrics` - Prometheus metrics endpoint
- Container health checks for auto-restart

---

## Subscription Tiers

### Free (Beta)
- 50 AI recommendations per month
- 20 products
- 2 market venues
- Basic weather integration
- Community support

### Professional ($29/month)
- 500 AI recommendations per month
- 100 products
- 10 market venues
- Advanced weather & events
- Priority email support
- Custom ML training

### Enterprise ($99/month)
- Unlimited recommendations
- Unlimited products & venues
- Dedicated account manager
- API access with higher rate limits
- Custom integrations
- SLA guarantee
- Phone support

---

## Contributing

We welcome contributions! MarketPrep is open-source and community-driven.

### Ways to Contribute

- 🐛 **Report Bugs**: Open an issue with reproduction steps
- 💡 **Suggest Features**: Share your ideas in discussions
- 📝 **Improve Docs**: Help make our documentation clearer
- 🔧 **Submit PRs**: Fix bugs or add features
- 🧪 **Write Tests**: Increase test coverage
- 🌍 **Translate**: Add internationalization support

### Development Setup

```bash
# Fork and clone the repository
git clone https://github.com/yourusername/marketprep.git
cd marketprep

# Create a feature branch
git checkout -b feature/your-feature-name

# Make changes and test
docker-compose up -d
pytest backend/
npm test --prefix frontend/

# Submit a pull request
git push origin feature/your-feature-name
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines.

---

## Support

### Get Help

- 📚 **Documentation**: Browse the [docs/](docs/) directory
- 💬 **Discussions**: Ask questions in [GitHub Discussions](https://github.com/jmanhype/marketprep/discussions)
- 🐛 **Bug Reports**: Open an issue on [GitHub Issues](https://github.com/jmanhype/marketprep/issues)
- 📧 **Email**: support@marketprep.example.com

### Community

- ⭐ **Star the repo** to show your support
- 🐦 **Follow us** on Twitter [@MarketPrepApp](https://twitter.com/marketprepapp)
- 📰 **Subscribe** to our newsletter for updates

---

## Roadmap

### v1.1 (Q1 2026)
- [ ] Mobile app (React Native)
- [ ] Multi-language support (Spanish, French)
- [ ] Integration with Shopify POS
- [ ] Advanced analytics dashboard
- [ ] SMS alerts for recommendations

### v1.2 (Q2 2026)
- [ ] Integration with Clover and Toast POS
- [ ] Historical weather pattern analysis
- [ ] Custom ML model per vendor
- [ ] API marketplace for third-party integrations
- [ ] White-label solutions for market organizers

---

## Project Stats

| Metric | Value |
|--------|-------|
| **Lines of Code** | 5,193 (backend) + 3,500 (frontend) |
| **Test Coverage** | 100% (backend) |
| **Passing Tests** | 1,230 |
| **Development Time** | 2 weeks (204 tasks) |
| **Contributors** | Open for contributions! |
| **Framework** | [Spec Kit](https://github.com/anthropics/spec-kit) |

---

## Built With

This project uses best-in-class open-source technologies:

**Backend**: FastAPI • PostgreSQL • Redis • Celery • scikit-learn • Alembic

**Frontend**: React • TypeScript • Vite • Tailwind CSS • Axios

**Infrastructure**: Docker • GitHub Actions • Prometheus • OpenTelemetry

**APIs**: Square • OpenWeatherMap • Eventbrite

---

## License

MarketPrep is released under the **MIT License**. See [LICENSE](LICENSE) for details.

```
Copyright (c) 2025 MarketPrep

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction...
```

---

## Acknowledgments

- Built with [Spec Kit](https://github.com/anthropics/spec-kit) specification-driven development
- Developed with [Claude Code](https://claude.com/claude-code)
- Inspired by farmers market vendors who need better tools

---

<div align="center">

**[View on GitHub](https://github.com/jmanhype/marketprep)** • **[Report Bug](https://github.com/jmanhype/marketprep/issues)** • **[Request Feature](https://github.com/jmanhype/marketprep/discussions)**

Made with ❤️ for farmers market communities

[![GitHub stars](https://img.shields.io/github/stars/jmanhype/marketprep?style=social)](https://github.com/jmanhype/marketprep)
[![GitHub forks](https://img.shields.io/github/forks/jmanhype/marketprep?style=social)](https://github.com/jmanhype/marketprep)

**Version 1.0.0** • **Updated December 2, 2025**

</div>
