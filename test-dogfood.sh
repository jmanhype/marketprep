#!/bin/bash
# MarketPrep Dogfooding Test Script
# This script validates the core user flows

set -e  # Exit on error

BASE_URL="http://localhost:8000"
FRONTEND_URL="http://localhost:3000"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test counter
TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

# Helper functions
test_start() {
    echo -e "${YELLOW}🧪 Testing: $1${NC}"
    TESTS_RUN=$((TESTS_RUN + 1))
}

test_pass() {
    echo -e "${GREEN}✅ PASS: $1${NC}"
    TESTS_PASSED=$((TESTS_PASSED + 1))
}

test_fail() {
    echo -e "${RED}❌ FAIL: $1${NC}"
    TESTS_FAILED=$((TESTS_FAILED + 1))
}

echo "========================================="
echo "MarketPrep Dogfooding Test Suite"
echo "========================================="
echo ""

# Phase 1: Infrastructure
echo "=== Phase 1: Infrastructure ==="

test_start "Backend health endpoint"
HEALTH=$(curl -s $BASE_URL/health | jq -r '.status')
if [ "$HEALTH" == "healthy" ]; then
    test_pass "Backend is healthy"
else
    test_fail "Backend health check failed"
fi

test_start "Frontend serving"
FRONTEND_STATUS=$(curl -s -o /dev/null -w "%{http_code}" $FRONTEND_URL)
if [ "$FRONTEND_STATUS" == "200" ]; then
    test_pass "Frontend is serving"
else
    test_fail "Frontend not accessible"
fi

test_start "OpenAPI docs"
DOCS_STATUS=$(curl -s -o /dev/null -w "%{http_code}" $BASE_URL/api/docs)
if [ "$DOCS_STATUS" == "200" ]; then
    test_pass "OpenAPI docs accessible at /api/docs"
else
    test_fail "OpenAPI docs not accessible"
fi

test_start "Redis connectivity"
if docker exec marketprep-redis redis-cli ping | grep -q "PONG"; then
    test_pass "Redis is responding"
else
    test_fail "Redis not responding"
fi

test_start "PostgreSQL connectivity"
if docker exec marketprep-postgres pg_isready -U marketprep | grep -q "accepting connections"; then
    test_pass "PostgreSQL is accepting connections"
else
    test_fail "PostgreSQL not accepting connections"
fi

echo ""

# Phase 2: Database Schema
echo "=== Phase 2: Database Schema ==="

test_start "Database tables exist"
TABLES=$(docker exec marketprep-postgres psql -U marketprep -d marketprep_dev -t -c "\dt" | wc -l)
if [ "$TABLES" -gt 5 ]; then
    test_pass "Database has tables ($TABLES found)"
else
    test_fail "Database tables missing"
fi

test_start "Vendors table"
if docker exec marketprep-postgres psql -U marketprep -d marketprep_dev -c "\d vendors" | grep -q "id"; then
    test_pass "Vendors table exists with correct schema"
else
    test_fail "Vendors table schema incorrect"
fi

test_start "Products table"
if docker exec marketprep-postgres psql -U marketprep -d marketprep_dev -c "\d products" | grep -q "product_id"; then
    test_pass "Products table exists"
else
    test_fail "Products table missing"
fi

test_start "Recommendations table"
if docker exec marketprep-postgres psql -U marketprep -d marketprep_dev -c "\d recommendations" | grep -q "recommendation_id"; then
    test_pass "Recommendations table exists"
else
    test_fail "Recommendations table missing"
fi

echo ""

# Phase 3: Authentication
echo "=== Phase 3: Authentication Flow ==="

test_start "User registration"
REGISTER_RESPONSE=$(curl -s -X POST $BASE_URL/api/v1/auth/register \
    -H "Content-Type: application/json" \
    -d '{
        "email": "dogfood@marketprep.test",
        "password": "SecurePassword123",
        "business_name": "Dogfood Farm Market"
    }')

if echo "$REGISTER_RESPONSE" | jq -e '.access_token' > /dev/null 2>&1; then
    test_pass "User registration successful"
    TOKEN=$(echo "$REGISTER_RESPONSE" | jq -r '.access_token')
else
    # Try login instead (user might already exist)
    test_start "User login (fallback)"
    LOGIN_RESPONSE=$(curl -s -X POST $BASE_URL/api/v1/auth/login \
        -H "Content-Type: application/json" \
        -d '{"email": "dogfood@marketprep.test", "password": "SecurePassword123"}')

    if echo "$LOGIN_RESPONSE" | jq -e '.access_token' > /dev/null 2>&1; then
        test_pass "User login successful"
        TOKEN=$(echo "$LOGIN_RESPONSE" | jq -r '.access_token')
    else
        test_fail "Authentication failed"
        TOKEN=""
    fi
fi

if [ -n "$TOKEN" ]; then
    test_start "Protected endpoint access"
    ME_RESPONSE=$(curl -s -H "Authorization: Bearer $TOKEN" $BASE_URL/api/v1/vendors/me)
    if echo "$ME_RESPONSE" | jq -e '.email' > /dev/null 2>&1; then
        test_pass "Can access protected endpoints with JWT"
    else
        test_fail "JWT authentication not working"
    fi
fi

echo ""

# Phase 4: API Endpoints
echo "=== Phase 4: Core API Endpoints ==="

if [ -n "$TOKEN" ]; then
    test_start "Products endpoint"
    PRODUCTS=$(curl -s -H "Authorization: Bearer $TOKEN" $BASE_URL/api/v1/products)
    if echo "$PRODUCTS" | jq -e 'type' > /dev/null 2>&1; then
        test_pass "Products endpoint returns valid JSON"
    else
        test_fail "Products endpoint failed"
    fi

    test_start "Sales endpoint"
    SALES=$(curl -s -H "Authorization: Bearer $TOKEN" $BASE_URL/api/v1/sales)
    if echo "$SALES" | jq -e 'type' > /dev/null 2>&1; then
        test_pass "Sales endpoint returns valid JSON"
    else
        test_fail "Sales endpoint failed"
    fi

    test_start "Recommendations endpoint"
    RECS=$(curl -s -H "Authorization: Bearer $TOKEN" "$BASE_URL/api/v1/recommendations?limit=10")
    if echo "$RECS" | jq -e 'type' > /dev/null 2>&1; then
        test_pass "Recommendations endpoint returns valid JSON"
    else
        test_fail "Recommendations endpoint failed"
    fi
fi

echo ""

# Phase 5: Metrics & Monitoring
echo "=== Phase 5: Metrics & Monitoring ==="

test_start "Prometheus metrics endpoint"
METRICS=$(curl -s $BASE_URL/metrics)
if echo "$METRICS" | grep -q "http_requests_total"; then
    test_pass "Prometheus metrics available"
else
    test_fail "Prometheus metrics not found"
fi

echo ""

# Phase 6: Error Handling
echo "=== Phase 6: Error Handling ==="

test_start "404 for invalid route"
STATUS_404=$(curl -s -o /dev/null -w "%{http_code}" $BASE_URL/invalid/route)
if [ "$STATUS_404" == "404" ]; then
    test_pass "404 errors handled correctly"
else
    test_fail "404 handling not working"
fi

test_start "401 for unauthorized access"
STATUS_401=$(curl -s -o /dev/null -w "%{http_code}" $BASE_URL/api/v1/vendors/me)
if [ "$STATUS_401" == "401" ]; then
    test_pass "401 errors for unauthorized requests"
else
    test_fail "Authorization not enforced"
fi

echo ""

# Summary
echo "========================================="
echo "Test Summary"
echo "========================================="
echo "Tests Run:    $TESTS_RUN"
echo -e "${GREEN}Tests Passed: $TESTS_PASSED${NC}"
echo -e "${RED}Tests Failed: $TESTS_FAILED${NC}"
echo ""

if [ "$TESTS_FAILED" -eq 0 ]; then
    echo -e "${GREEN}🎉 All tests passed! Application is working correctly.${NC}"
    echo ""
    echo "✅ You can now access:"
    echo "   - Frontend: $FRONTEND_URL"
    echo "   - Backend:  $BASE_URL"
    echo "   - API Docs: $BASE_URL/docs"
    exit 0
else
    echo -e "${RED}⚠️  Some tests failed. Please review the output above.${NC}"
    exit 1
fi
