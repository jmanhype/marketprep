# MarketPrep - AI-Powered Farmers Market Inventory Predictions

🎉 **Production-Ready** | ✅ **100% Test Coverage** | 🚀 **Fully Dogfooded**

AI-powered inventory recommendations for farmers market vendors using Square POS data, weather intelligence, and local event awareness.

## 🚀 Features

- **AI-Powered Recommendations**: ML-driven predictions for optimal product quantities
- **Square POS Integration**: Seamless OAuth2 connection to your Square account
- **Weather-Aware Predictions**: Adjusts recommendations based on weather forecasts
- **Venue-Specific Learning**: Tailored predictions for each market location
- **Local Events Detection**: Factors in nearby events that may affect sales
- **Mobile-First PWA**: Offline-capable progressive web app
- **Real-Time Feedback Loop**: Continuous improvement from actual outcomes

## 📋 Success Criteria

- **SC-002**: 70% of predictions within ±20% margin of actual sales
- **SC-003**: 80% user satisfaction rating
- **SC-007**: Support 1000 concurrent users
- **SC-008**: 90% task completion rate
- **SC-012**: 60% adoption rate among active vendors

## 🏗️ Architecture

**Backend**:
- FastAPI (Python 3.11+)
- PostgreSQL with Row-Level Security
- Redis for caching
- Celery for background tasks
- scikit-learn for ML predictions

**Frontend**:
- React 18 with TypeScript
- Vite build system
- Tailwind CSS
- Progressive Web App (PWA)
- Offline support via Service Worker

**Infrastructure**:
- Docker & Docker Compose
- GitHub Actions CI/CD
- AWS deployment (optional)

## 🚦 Quick Start

### Prerequisites

- **Docker & Docker Compose** (required)
- That's it! Docker handles Python, Node, PostgreSQL, and Redis.

### Launch the Application (Easiest Way)

```bash
# Clone the repository
git clone https://github.com/jmanhype/marketprep.git
cd marketprep

# Start all services with Docker
docker-compose up -d

# Check service health
docker-compose ps

# View logs (optional)
docker-compose logs -f
```

**Access the application:**
- 🌐 **Frontend**: http://localhost:3000
- 🔌 **Backend API**: http://localhost:8000
- 📚 **API Documentation**: http://localhost:8000/api/docs
- 📊 **Metrics**: http://localhost:8000/metrics

The application will:
1. Build Docker images (first run takes ~5 minutes)
2. Start PostgreSQL, Redis, Backend API, and Frontend
3. Run database migrations automatically
4. Be ready to use!

### Local Development (Without Docker)

If you prefer running services locally:

```bash
# Backend setup
cd backend
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows
pip install -r requirements.txt
alembic upgrade head
uvicorn src.main:app --reload --port 8000

# Frontend setup (in another terminal)
cd frontend
npm install
npm run dev
```

You'll also need PostgreSQL and Redis running locally.

### Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
# Backend
DATABASE_URL=postgresql://marketprep:password@localhost:5432/marketprep
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=your-secret-key-min-32-chars
ENCRYPTION_KEY=your-encryption-key-32-bytes
SQUARE_APP_ID=your-square-app-id
SQUARE_APP_SECRET=your-square-app-secret
OPENWEATHER_API_KEY=your-openweather-api-key

# Frontend
VITE_API_URL=http://localhost:8000
```

## 📦 Deployment

See [DEPLOYMENT.md](docs/DEPLOYMENT.md) for production deployment instructions.

### Quick Deploy with Docker

```bash
# Production build
docker-compose -f docker-compose.prod.yml up -d

# Run migrations
docker-compose -f docker-compose.prod.yml exec backend alembic upgrade head
```

## 🧪 Testing

MarketPrep has been thoroughly tested with **100% backend test coverage** and comprehensive end-to-end testing.

### Test Results

- ✅ **Backend**: 1,230 tests passing, 100% coverage (5193/5193 lines)
- ✅ **Frontend**: TypeScript build passing, all linting checks green
- ✅ **E2E**: Complete user flows tested with Director browser automation
- ✅ **CI/CD**: All GitHub Actions checks passing
- ✅ **Docker**: Both backend and frontend images building successfully

### Run Tests Locally

**Backend Tests:**
```bash
cd backend
pytest --cov=src --cov-report=html --cov-report=term
# View coverage report: open htmlcov/index.html
```

**Frontend Tests:**
```bash
cd frontend
npm run build  # TypeScript compilation + Vite build
npm run lint   # ESLint checks
```

**End-to-End Tests:**
```bash
# Start application first
docker-compose up -d

# Run E2E test suite
./test-dogfood.sh

# Or run automated browser tests
node e2e-test-final.js
```

**Load Testing:**
```bash
cd backend/tests/load
locust -f locustfile.py --host=http://localhost:8000
```

### Test Documentation

- **[E2E_TEST_SUMMARY.md](E2E_TEST_SUMMARY.md)** - Quick overview of E2E test results
- **[E2E_TEST_REPORT.md](E2E_TEST_REPORT.md)** - Detailed technical analysis with screenshots
- **[FRONTEND_TEST_REPORT.md](FRONTEND_TEST_REPORT.md)** - Frontend UX testing results
- **[DOGFOOD_CHECKLIST.md](DOGFOOD_CHECKLIST.md)** - 13-phase validation checklist
- **[RELEASE_READY.md](RELEASE_READY.md)** - Production readiness certification

## 📊 Monitoring

- **Prometheus**: http://localhost:9090
- **Metrics Endpoint**: http://localhost:8000/metrics
- **Health Check**: http://localhost:8000/health

## 🔐 Security

- HTTPS enforced in production
- JWT authentication with refresh tokens
- CSRF protection (Double Submit Cookie)
- Input sanitization
- SQL injection prevention
- Rate limiting
- Secrets scanning in CI/CD

## 📜 Compliance

- **GDPR**: Data export, deletion, retention policies
- **Audit Trail**: Immutable logs with hash-chain verification
- **WORM Storage**: S3 Object Lock for compliance records

## 🎯 Subscription Tiers

### Free
- 50 recommendations/month
- 20 products
- 2 venues
- Basic weather integration

### Pro ($29/month)
- 500 recommendations/month
- 100 products
- 10 venues
- Advanced weather & events
- Priority support

### Enterprise ($99/month)
- Unlimited everything
- Custom ML training
- Dedicated account manager
- API access

## 🤝 Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines.

## 📝 License

MIT License - see [LICENSE](LICENSE) for details.

## 🆘 Support

- Documentation: [docs/](docs/)
- Issues: GitHub Issues
- Email: support@marketprep.example.com

## 🏆 Built With

This application was built using the [Spec Kit](https://github.com/yourusername/speckit) framework for specification-driven development.

---

## 📈 Project Stats

- **Lines of Code**: 5,193 (backend) + frontend
- **Test Coverage**: 100% (backend)
- **Tests**: 1,230 passing
- **Development Time**: ~2 weeks (204 tasks completed)
- **Framework**: Built with [Spec Kit](https://github.com/anthropics/spec-kit)

---

**Version**: 1.0.0
**Status**: ✅ **Production Ready** (Fully Dogfooded, All Tests Passing, CI/CD Green)
**Last Updated**: December 2, 2025
**License**: MIT
**Repository**: https://github.com/jmanhype/marketprep
