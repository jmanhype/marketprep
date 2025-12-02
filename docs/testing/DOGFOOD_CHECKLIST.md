# MarketPrep Dogfooding Checklist

**Purpose**: Validate 100% functionality before making the project public
**Date**: December 2, 2025

## Pre-Flight Checks

### Environment Setup
- [ ] Docker and Docker Compose installed
- [ ] Ports available: 5433 (PostgreSQL), 6379 (Redis), 8000 (Backend), 3000 (Frontend)
- [ ] `.env` file configured with API keys (optional for basic testing)

### Build & Deploy
- [ ] `docker-compose build` - All images build successfully
- [ ] `docker-compose up -d` - All services start without errors
- [ ] Health checks pass for postgres, redis, backend, frontend
- [ ] No errors in docker logs

## Phase 1: Infrastructure Validation

### Database
- [ ] PostgreSQL container running
- [ ] Database `marketprep_dev` created
- [ ] Can connect: `psql -h localhost -p 5433 -U marketprep -d marketprep_dev`
- [ ] Alembic migrations applied successfully
- [ ] All tables created (vendors, products, sales, recommendations, etc.)
- [ ] Row-Level Security (RLS) policies active

### Redis
- [ ] Redis container running
- [ ] Can connect: `redis-cli -p 6379 ping` returns PONG
- [ ] Cache operations working

### Backend API
- [ ] Backend container running on port 8000
- [ ] Health endpoint: `GET http://localhost:8000/health` returns 200
- [ ] OpenAPI docs: `http://localhost:8000/docs` loads
- [ ] No startup errors in logs

### Frontend
- [ ] Frontend container running on port 3000
- [ ] App loads: `http://localhost:3000` shows UI
- [ ] No console errors
- [ ] Service worker registers (PWA)

## Phase 2: Authentication & Authorization

### User Registration
- [ ] Can access registration page
- [ ] Required fields: email, password, business_name
- [ ] Email validation works
- [ ] Password strength validation works
- [ ] Registration creates vendor account
- [ ] Automatic login after registration

### User Login
- [ ] Can access login page
- [ ] Login with valid credentials works
- [ ] Login with invalid credentials fails appropriately
- [ ] JWT token stored in localStorage
- [ ] Auto-redirect to dashboard after login

### Session Management
- [ ] Token auto-refresh works
- [ ] Logout clears session
- [ ] Protected routes redirect to login when unauthenticated
- [ ] Session persists on page refresh

## Phase 3: Square POS Integration

### Square OAuth Flow
- [ ] "Connect Square POS" button visible in Settings
- [ ] Click initiates OAuth flow
- [ ] Square login page loads (or sandbox)
- [ ] After authorization, redirects back to app
- [ ] OAuth callback handles state parameter correctly
- [ ] Square access token stored (encrypted)
- [ ] Connection status shows "Connected"

### Square Data Sync
- [ ] Manual sync button available
- [ ] Click "Sync Products" fetches catalog
- [ ] Products appear in Products page
- [ ] Product details accurate (name, price, category)
- [ ] Click "Sync Sales" fetches transactions
- [ ] Sales data appears in dashboard
- [ ] Sales metrics calculate correctly

### Error Handling
- [ ] Expired token detection works
- [ ] Re-authorization prompt appears
- [ ] Failed sync shows user-friendly error
- [ ] Graceful fallback to cached data

## Phase 4: AI Recommendations (Core MVP)

### Generate Recommendations
- [ ] Navigate to Recommendations page
- [ ] Date picker shows upcoming dates
- [ ] Select a date in the future
- [ ] Click "Generate Recommendations"
- [ ] Loading indicator shows
- [ ] Recommendations appear within reasonable time (<5s)

### Recommendation Quality
- [ ] Each product has predicted quantity
- [ ] Confidence level shown (high/medium/low)
- [ ] Recommendations based on historical sales
- [ ] Products with no history show conservative estimates
- [ ] Total items count displayed

### Recommendation Details
- [ ] Product name, image, category shown
- [ ] Recommended quantity is a reasonable number
- [ ] Explanation provided ("Based on past sales...")
- [ ] Can expand to see more details

## Phase 5: Weather-Aware Predictions

### Weather Integration
- [ ] Weather forecast shown for selected date
- [ ] Temperature, conditions, humidity displayed
- [ ] Weather icon matches conditions
- [ ] Forecast data comes from OpenWeatherMap API
- [ ] Fallback to historical average if API fails

### Weather Impact
- [ ] Recommendations differ on rainy vs sunny days
- [ ] Cold weather boosts warm food predictions
- [ ] Hot weather boosts cold beverage predictions
- [ ] Weather explanation in recommendation details

## Phase 6: Venue-Specific Learning

### Venue Management
- [ ] Can add venue (name, location)
- [ ] Can edit venue details
- [ ] Can view sales history per venue
- [ ] Venue selector on recommendations page

### Venue-Specific Predictions
- [ ] Select different venues for same date
- [ ] Recommendations differ by venue
- [ ] High-confidence for venues with history
- [ ] Low-confidence warning for new venues
- [ ] "Data stale" warning for venues unused 6+ months

## Phase 7: Local Events Detection

### Events Integration
- [ ] Events shown for selected date/location
- [ ] Event details: name, date, attendees, distance
- [ ] Events fetched from Eventbrite API
- [ ] Can manually add local events
- [ ] Events saved to database

### Event Impact
- [ ] High-attendance events boost predictions
- [ ] Event notification badge shown
- [ ] Event details in recommendation explanation
- [ ] Recommendations increase for major events

## Phase 8: Mobile Experience

### Responsive Design
- [ ] Open on mobile device (or DevTools mobile view)
- [ ] All text readable without zooming
- [ ] Buttons easily tappable (44px+ touch targets)
- [ ] Navigation accessible on mobile
- [ ] Forms work on mobile keyboard

### PWA Features
- [ ] "Add to Home Screen" prompt appears
- [ ] App icon shows on home screen
- [ ] Opens fullscreen (no browser chrome)
- [ ] Offline indicator shows when disconnected
- [ ] Cached data available offline
- [ ] Recommendations persist offline after initial load

### Performance
- [ ] Pages load quickly on mobile (<3s)
- [ ] No layout shift on load
- [ ] Images optimized for mobile
- [ ] Lazy loading works for route components

## Phase 9: Production Features

### Feedback Loop
- [ ] Can submit feedback on recommendation accuracy
- [ ] Feedback form has actual vs predicted quantities
- [ ] Feedback saves successfully
- [ ] Model retraining scheduled (check logs)

### Subscription & Billing
- [ ] Subscription tier shown in settings
- [ ] Upgrade prompt for premium features
- [ ] Stripe integration configured
- [ ] Payment flow works (test mode)

### Monitoring & Observability
- [ ] Prometheus metrics endpoint: `http://localhost:8000/metrics`
- [ ] Metrics include request counts, latencies
- [ ] Logs structured with correlation IDs
- [ ] Error tracking to Sentry (if configured)

### Security
- [ ] CSRF token validation works
- [ ] Input sanitization prevents XSS
- [ ] SQL injection prevented (parameterized queries)
- [ ] Secrets not in logs or error messages
- [ ] Rate limiting active (try 100 rapid requests)

### Compliance
- [ ] Data export works (GDPR right to access)
- [ ] Account deletion works (GDPR right to deletion)
- [ ] Audit log records all API calls
- [ ] Audit log hash-chain verifiable
- [ ] Retention policy configurable

## Phase 10: Error Scenarios

### Graceful Degradation
- [ ] Square API down → uses cached data
- [ ] Weather API down → uses historical average
- [ ] Events API down → skips event detection
- [ ] Redis down → falls back to in-memory cache
- [ ] Database slow → request times out gracefully

### User-Facing Errors
- [ ] Network errors show friendly message
- [ ] Form validation errors clear and helpful
- [ ] 404 page for invalid routes
- [ ] 500 errors don't expose internals
- [ ] Retry button for failed operations

## Phase 11: Data Quality

### Test Data
- [ ] Create test vendor account
- [ ] Import 30+ days of sales history
- [ ] Multiple products (10+)
- [ ] Multiple venues (3+)
- [ ] Sales on different days of week
- [ ] Sales in different weather conditions

### Prediction Accuracy
- [ ] Compare predictions to actual sales
- [ ] Accuracy within 20% margin (SC-002 target: 70%)
- [ ] Confidence scores correlate with accuracy
- [ ] Predictions improve with more data

## Phase 12: Performance

### Load Testing
- [ ] Backend handles 100 concurrent users
- [ ] No memory leaks over time
- [ ] Database queries optimized (no N+1)
- [ ] Response times <500ms for critical paths
- [ ] Frontend bundle size reasonable (<500KB gzipped)

### Accessibility
- [ ] WCAG 2.1 AA compliant
- [ ] Keyboard navigation works
- [ ] Screen reader compatible
- [ ] Color contrast ratio ≥4.5:1
- [ ] Focus indicators visible

## Phase 13: Documentation

### User Documentation
- [ ] README explains what MarketPrep does
- [ ] Setup instructions accurate and complete
- [ ] API documentation generated and accurate
- [ ] Environment variables documented

### Developer Documentation
- [ ] Architecture documented
- [ ] Database schema documented
- [ ] API contracts up to date
- [ ] Deployment guide accurate

## Sign-Off

### Final Checks
- [ ] All tests passing (100% coverage verified)
- [ ] All CI checks green
- [ ] Docker images build successfully
- [ ] No known critical bugs
- [ ] Performance acceptable
- [ ] Security scan clean
- [ ] Ready for public release

### Tested By
- Name: ___________________
- Date: ___________________
- Verdict: [ ] PASS / [ ] FAIL

### Issues Found
(List any issues discovered during dogfooding)

1.
2.
3.

---

**Note**: This checklist should be completed in order. Any failures must be fixed before proceeding to make the project public.
