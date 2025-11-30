# MarketPrep - Market Inventory Predictor

AI-powered inventory recommendations for farmers market vendors using Square POS data.

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

- Docker & Docker Compose
- Python 3.11+
- Node.js 18+
- PostgreSQL 15+
- Redis 7+

### Local Development

```bash
# Start infrastructure
docker-compose up -d

# Backend setup
cd backend
pip install -r requirements.txt
alembic upgrade head
uvicorn src.main:app --reload

# Frontend setup
cd frontend
npm install
npm run dev
```

Visit http://localhost:3000

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

### Backend Tests

```bash
cd backend
pytest --cov=src --cov-report=html
```

### Frontend Tests

```bash
cd frontend
npm test -- --coverage
```

### Load Testing

```bash
cd backend/tests/load
locust -f locustfile.py
```

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

**Version**: 1.0.0
**Status**: Production Ready ✅
**Last Updated**: 2024-11-30
