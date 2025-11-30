# Frontend-Backend Sync Status

**Date**: 2025-11-30
**Session**: Code archaeology and gap fixing

## Backend Changes Made

This session added/fixed the following backend endpoints:

### 1. Registration Endpoint ✓
**Endpoint**: `POST /api/v1/auth/register`
```typescript
{
  email: string;
  password: string;
  business_name: string;
}
→ Returns: { access_token, refresh_token, vendor }
```

### 2. Venues Management ✓
**Endpoints**: Full CRUD at `/api/v1/venues`
- `GET /venues` - List vendor's venues
- `POST /venues` - Create new venue
- `GET /venues/{id}` - Get venue details
- `PATCH /venues/{id}` - Update venue
- `DELETE /venues/{id}` - Delete venue

### 3. Vendor Profile ✓
**Endpoint**: `PATCH /api/v1/vendors/me`
- Update business_name, phone
- Returns updated vendor object

### 4. Recommendations (ALREADY COMPATIBLE) ✓
- Frontend already uses `POST /recommendations/generate` ✓
- No changes needed (just verification)

---

## Frontend Gaps Identified

### Critical Missing Features (P1)

#### 1. Registration Page ❌
**Status**: Missing
**Backend**: Ready ✓
**Frontend**: Not implemented

**What's needed**:
- [ ] `RegisterPage.tsx` - Registration form component
- [ ] Update `AuthContext.tsx` - Add `register()` function
- [ ] Update `router.tsx` - Add `/auth/register` route
- [ ] Update `LoginPage.tsx` - Add registration link

**User impact**: New vendors cannot sign up without API tools

**Task**: `speckit-3o0`

---

#### 2. Venues Management Page ❌
**Status**: Missing
**Backend**: Ready ✓
**Frontend**: Not implemented

**What exists**:
- ✓ `VenueWarning.tsx` component (display only)

**What's needed**:
- [ ] `VenuesPage.tsx` - Full venue management UI
- [ ] `venueService.ts` - API client service
- [ ] Update `router.tsx` - Add `/venues` route
- [ ] Update navigation - Add "Venues" link

**User impact**: Multi-venue vendors cannot manage locations

**Task**: `speckit-eje`

---

### Important Enhancements (P2)

#### 3. Vendor Profile Editing ⚠️
**Status**: Minimal (862 bytes stub)
**Backend**: Ready ✓
**Frontend**: Needs expansion

**What exists**:
- ✓ `SettingsPage.tsx` (minimal stub)

**What's needed**:
- [ ] Expand `SettingsPage.tsx` - Add profile form
- [ ] Profile fields: business_name, email (readonly), phone
- [ ] Save functionality with success/error feedback

**User impact**: Vendors cannot update their profile

**Task**: `speckit-x17`

---

#### 4. API Endpoint Verification ⚠️
**Status**: Needs verification
**Backend**: Updated ✓
**Frontend**: Probably compatible

**What's needed**:
- [ ] Verify `RecommendationsPage.tsx` uses correct endpoints
- [ ] Check feedback submission uses PUT not POST
- [ ] Test end-to-end flow

**User impact**: Low (likely already working)

**Task**: `speckit-azb`

---

## Implementation Priority

### Phase 1: Critical User Flows (P1) - 3 hours
1. **Registration** (`speckit-3o0`) - 1 hour
   - Blocking new user onboarding
   - High visibility gap

2. **Venues Management** (`speckit-eje`) - 2 hours
   - Blocking multi-venue feature
   - Core functionality gap

### Phase 2: Enhancements (P2) - 1.5 hours
3. **Profile Editing** (`speckit-x17`) - 1 hour
   - Improves UX
   - Standard feature expectation

4. **API Verification** (`speckit-azb`) - 30 minutes
   - Low risk (likely working)
   - Quick validation

**Total time**: 4.5 hours

---

## File Inventory

### Files to Create
```
frontend/src/pages/RegisterPage.tsx          (NEW)
frontend/src/pages/VenuesPage.tsx            (NEW)
frontend/src/services/venueService.ts        (NEW)
```

### Files to Modify
```
frontend/src/contexts/AuthContext.tsx        (add register())
frontend/src/router.tsx                      (add routes)
frontend/src/pages/LoginPage.tsx             (add registration link)
frontend/src/pages/SettingsPage.tsx          (expand profile form)
frontend/src/layouts/DashboardLayout.tsx     (add venues nav link)
```

### Files to Verify
```
frontend/src/pages/RecommendationsPage.tsx   (check API calls)
frontend/src/components/FeedbackForm.tsx     (if exists)
```

---

## Testing Checklist

### Registration Flow
- [ ] User can access /auth/register
- [ ] Registration form validates inputs
- [ ] Successful registration redirects to dashboard
- [ ] Error messages display correctly
- [ ] Tokens stored in localStorage
- [ ] Login link works from registration page

### Venues Management
- [ ] User can view all venues
- [ ] User can create new venue
- [ ] User can edit existing venue
- [ ] User can delete venue with confirmation
- [ ] User can toggle venue active/inactive
- [ ] Venues appear in recommendations dropdown

### Profile Editing
- [ ] User can update business name
- [ ] User can update phone number
- [ ] Email is read-only
- [ ] Subscription info is read-only
- [ ] Changes save successfully
- [ ] Success message displays
- [ ] Profile updates reflect in header/nav

### API Compatibility
- [ ] Recommendations generate successfully
- [ ] Feedback submission works
- [ ] No console errors from API calls
- [ ] All endpoints return expected data

---

## Beads Tracking

**Epic**: `speckit-wev` - Complete frontend-backend sync

**Subtasks**:
- `speckit-3o0` [P1] - Registration page
- `speckit-eje` [P1] - Venues management
- `speckit-x17` [P2] - Profile editing
- `speckit-azb` [P2] - API verification

**Status**: 0/4 complete
**Time estimate**: 4.5 hours
**Priority**: P1 (blocking user features)

---

## Backend Compatibility Matrix

| Feature | Backend Endpoint | Frontend Component | Status |
|---------|-----------------|-------------------|--------|
| Login | POST /auth/login | LoginPage.tsx | ✅ Working |
| **Registration** | POST /auth/register | ❌ Missing | 🔴 Gap |
| Recommendations | POST /recommendations/generate | RecommendationsPage.tsx | ✅ Working |
| **Venues List** | GET /venues | ❌ Missing | 🔴 Gap |
| **Venues CRUD** | POST/PATCH/DELETE /venues | ❌ Missing | 🔴 Gap |
| **Profile Edit** | PATCH /vendors/me | ⚠️ Stub only | 🟡 Incomplete |
| Products | GET /products | ProductsPage.tsx | ✅ Working |
| Square OAuth | GET /auth/square/connect | SquareSettingsPage.tsx | ✅ Working |
| Feedback | PUT /recommendations/{id}/feedback | RecommendationsPage.tsx | 🟡 Verify |

**Legend**:
- ✅ Complete and working
- 🟡 Exists but needs verification/expansion
- 🔴 Missing implementation
- ❌ Not implemented

---

## Success Criteria

Frontend-backend sync is complete when:
- ✅ All backend endpoints have corresponding UI
- ✅ All CRUD operations accessible via frontend
- ✅ No features require direct API calls
- ✅ User can complete all core workflows in browser
- ✅ All API calls use correct endpoint patterns
- ✅ Registration, venues, and profile editing functional

**Current**: 2/4 tasks complete
**Target**: 4/4 tasks complete
**ETA**: 4.5 hours focused work
