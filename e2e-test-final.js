const playwright = require('playwright');
const fs = require('fs');
const path = require('path');

const screenshotDir = path.join(__dirname, 'e2e-test-screenshots');

// Ensure screenshot directory exists
if (!fs.existsSync(screenshotDir)) {
  fs.mkdirSync(screenshotDir, { recursive: true });
}

// Generate unique test email to avoid conflicts
const testEmail = `e2etest${Date.now()}@gmail.com`;
const testPassword = 'TestPass123!';
const testBusinessName = 'E2E Test Farm';

async function runE2ETest() {
  console.log('Starting MarketPrep FINAL E2E Test...');
  console.log(`Test credentials: ${testEmail} / ${testPassword}\n`);

  const browser = await playwright.chromium.launch({ headless: false });
  const context = await browser.newContext();
  const page = await context.newPage();

  const results = {
    testCredentials: { email: testEmail, password: testPassword, businessName: testBusinessName },
    registration: { success: false, error: null },
    login: { success: false, error: null },
    dashboard: { success: false, error: null, features: [], uiElements: {} },
    products: { success: false, error: null, features: [], uiElements: {} },
    recommendations: { success: false, error: null, features: [], uiElements: {} },
    settings: { success: false, error: null, features: [], uiElements: {} },
    logout: { success: false, error: null }
  };

  try {
    // =========================
    // 1. REGISTRATION FLOW
    // =========================
    console.log('=== 1. TESTING REGISTRATION FLOW ===');
    await page.goto('http://localhost:3000/auth/register');
    await page.waitForLoadState('networkidle');
    await page.screenshot({ path: path.join(screenshotDir, 'final-1-registration-page.png'), fullPage: true });
    console.log('✓ Registration page loaded');

    // Fill out registration form
    await page.fill('input[placeholder="Your Farm or Business"]', testBusinessName);
    await page.fill('input[placeholder="vendor@example.com"]', testEmail);
    const passwordFields = await page.locator('input[type="password"]').all();
    await passwordFields[0].fill(testPassword);
    await passwordFields[1].fill(testPassword);

    await page.screenshot({ path: path.join(screenshotDir, 'final-2-registration-filled.png'), fullPage: true });
    console.log('✓ Registration form filled');

    // Submit registration
    await page.click('button:has-text("Create Account")');
    await page.waitForTimeout(3000); // Wait for submission and redirect

    const errorMessage = await page.locator('.error, [role="alert"], .text-red-500, .text-red-600').allTextContents().catch(() => []);

    await page.screenshot({ path: path.join(screenshotDir, 'final-3-after-registration.png'), fullPage: true });

    const currentUrl = page.url();
    console.log(`After registration, redirected to: ${currentUrl}`);

    if (errorMessage.length > 0) {
      console.log(`Error messages: ${errorMessage.join(', ')}`);
      results.registration.errorMessages = errorMessage;
    }

    results.registration.redirectUrl = currentUrl;
    results.registration.success = !currentUrl.includes('/register') && errorMessage.length === 0;

    if (results.registration.success) {
      console.log('✓ Registration successful!');
    } else {
      console.log('✗ Registration failed');
    }

    // =========================
    // 2. LOGIN FLOW (if needed)
    // =========================
    console.log('\n=== 2. TESTING LOGIN FLOW ===');

    const isOnLoginPage = page.url().includes('/auth/login');

    if (isOnLoginPage) {
      console.log('Redirected to login page after registration');
      await page.fill('input[type="email"]', testEmail);
      await page.fill('input[type="password"]', testPassword);
      await page.screenshot({ path: path.join(screenshotDir, 'final-4-login-filled.png'), fullPage: true });

      await page.click('button:has-text("Sign In")');
      await page.waitForTimeout(3000);

      const loginErrorMessage = await page.locator('.error, [role="alert"], .text-red-500, .text-red-600').allTextContents().catch(() => []);

      await page.screenshot({ path: path.join(screenshotDir, 'final-5-after-login.png'), fullPage: true });

      console.log(`After login, current URL: ${page.url()}`);

      results.login.redirectUrl = page.url();
      results.login.success = !page.url().includes('/auth/') && loginErrorMessage.length === 0;

      if (loginErrorMessage.length > 0) {
        console.log(`Login error: ${loginErrorMessage.join(', ')}`);
        results.login.errorMessages = loginErrorMessage;
      }

      if (results.login.success) {
        console.log('✓ Login successful!');
      } else {
        console.log('✗ Login failed');
      }
    } else {
      console.log('Auto-logged in after registration');
      results.login.success = true;
      results.login.note = 'Auto-logged in after registration';
    }

    const isAuthenticated = !page.url().includes('/auth/');

    if (!isAuthenticated) {
      console.log('\n⚠️  Not authenticated - cannot test protected routes');
      results.dashboard.error = 'Authentication failed';
      results.products.error = 'Authentication failed';
      results.recommendations.error = 'Authentication failed';
      results.settings.error = 'Authentication failed';
    } else {
      // =========================
      // 3. DASHBOARD ACCESS
      // =========================
      console.log('\n=== 3. TESTING DASHBOARD ACCESS ===');

      if (!page.url().includes('/dashboard')) {
        await page.goto('http://localhost:3000/dashboard');
        await page.waitForLoadState('networkidle');
      }

      await page.screenshot({ path: path.join(screenshotDir, 'final-6-dashboard.png'), fullPage: true });

      const dashboardTitle = await page.locator('h1, h2').first().textContent().catch(() => 'No title');
      const dashboardContent = await page.textContent('body');
      const hasWelcomeMessage = dashboardContent.includes('Welcome') || dashboardContent.includes('Dashboard');
      const buttons = await page.locator('button').count();
      const links = await page.locator('a').count();
      const navigation = await page.locator('nav').count();

      results.dashboard.success = true;
      results.dashboard.features = [
        `Page title: ${dashboardTitle}`,
        `Welcome message: ${hasWelcomeMessage}`,
        `Navigation present: ${navigation > 0}`
      ];
      results.dashboard.uiElements = {
        buttons,
        links,
        navigation,
        hasContent: dashboardContent.length > 100
      };

      console.log(`✓ Dashboard loaded - Title: "${dashboardTitle}"`);
      console.log(`  - ${buttons} buttons, ${links} links, ${navigation} nav elements`);

      // =========================
      // 4. PRODUCTS PAGE
      // =========================
      console.log('\n=== 4. TESTING PRODUCTS PAGE ===');

      await page.goto('http://localhost:3000/products');
      await page.waitForLoadState('networkidle');
      await page.screenshot({ path: path.join(screenshotDir, 'final-7-products.png'), fullPage: true });

      const productsTitle = await page.locator('h1, h2').first().textContent().catch(() => 'No title');
      const productsContent = await page.textContent('body');
      const hasProductList = productsContent.includes('Product') || productsContent.includes('Inventory');
      const productButtons = await page.locator('button').count();
      const forms = await page.locator('form').count();
      const tables = await page.locator('table').count();

      results.products.success = true;
      results.products.features = [
        `Page title: ${productsTitle}`,
        `Product features visible: ${hasProductList}`,
        `Forms present: ${forms > 0}`,
        `Tables present: ${tables > 0}`
      ];
      results.products.uiElements = {
        buttons: productButtons,
        forms,
        tables,
        hasContent: productsContent.length > 100
      };

      console.log(`✓ Products page loaded - Title: "${productsTitle}"`);
      console.log(`  - ${productButtons} buttons, ${forms} forms, ${tables} tables`);

      // =========================
      // 5. RECOMMENDATIONS PAGE
      // =========================
      console.log('\n=== 5. TESTING RECOMMENDATIONS PAGE ===');

      await page.goto('http://localhost:3000/recommendations');
      await page.waitForLoadState('networkidle');
      await page.screenshot({ path: path.join(screenshotDir, 'final-8-recommendations.png'), fullPage: true });

      const recsTitle = await page.locator('h1, h2').first().textContent().catch(() => 'No title');
      const recsContent = await page.textContent('body');
      const hasRecommendations = recsContent.includes('Recommendation') || recsContent.includes('Predict') || recsContent.includes('AI');
      const recsButtons = await page.locator('button').count();
      const recsCards = await page.locator('[class*="card"], .card, [class*="Card"]').count();

      results.recommendations.success = true;
      results.recommendations.features = [
        `Page title: ${recsTitle}`,
        `Recommendations visible: ${hasRecommendations}`,
        `Cards present: ${recsCards > 0}`
      ];
      results.recommendations.uiElements = {
        buttons: recsButtons,
        cards: recsCards,
        hasContent: recsContent.length > 100
      };

      console.log(`✓ Recommendations page loaded - Title: "${recsTitle}"`);
      console.log(`  - ${recsButtons} buttons, ${recsCards} cards`);

      // =========================
      // 6. SETTINGS PAGE
      // =========================
      console.log('\n=== 6. TESTING SETTINGS PAGE ===');

      await page.goto('http://localhost:3000/settings');
      await page.waitForLoadState('networkidle');
      await page.screenshot({ path: path.join(screenshotDir, 'final-9-settings.png'), fullPage: true });

      const settingsTitle = await page.locator('h1, h2').first().textContent().catch(() => 'No title');
      const settingsContent = await page.textContent('body');
      const hasUserInfo = settingsContent.includes(testBusinessName) || settingsContent.includes(testEmail);
      const hasSquare = settingsContent.toLowerCase().includes('square') || settingsContent.toLowerCase().includes('pos');
      const settingsForms = await page.locator('form').count();
      const settingsInputs = await page.locator('input').count();

      results.settings.success = true;
      results.settings.features = [
        `Page title: ${settingsTitle}`,
        `User info displayed: ${hasUserInfo}`,
        `Square POS integration: ${hasSquare}`,
        `Settings forms: ${settingsForms > 0}`
      ];
      results.settings.uiElements = {
        forms: settingsForms,
        inputs: settingsInputs,
        hasSquareIntegration: hasSquare,
        hasUserInfo
      };

      console.log(`✓ Settings page loaded - Title: "${settingsTitle}"`);
      console.log(`  - User info visible: ${hasUserInfo}, Square integration: ${hasSquare}`);

      // =========================
      // 7. LOGOUT TEST
      // =========================
      console.log('\n=== 7. TESTING LOGOUT ===');

      // Look for logout button in various locations
      const logoutSelectors = [
        'button:has-text("Logout")',
        'button:has-text("Log Out")',
        'button:has-text("Sign Out")',
        'a:has-text("Logout")',
        'a:has-text("Log Out")',
        'a:has-text("Sign Out")',
        '[data-testid="logout"]',
        '[aria-label*="logout" i]',
        '[aria-label*="sign out" i]'
      ];

      let logoutButton = null;
      for (const selector of logoutSelectors) {
        const count = await page.locator(selector).count();
        if (count > 0) {
          logoutButton = page.locator(selector).first();
          console.log(`Found logout button with selector: ${selector}`);
          break;
        }
      }

      if (logoutButton) {
        await logoutButton.click();
        await page.waitForTimeout(2000);
        await page.screenshot({ path: path.join(screenshotDir, 'final-10-after-logout.png'), fullPage: true });

        const finalUrl = page.url();
        const isLoggedOut = finalUrl.includes('/auth/login') || finalUrl.includes('/auth/register');

        results.logout.success = isLoggedOut;
        results.logout.redirectUrl = finalUrl;

        if (isLoggedOut) {
          console.log(`✓ Logout successful, redirected to: ${finalUrl}`);
        } else {
          console.log(`✗ Logout failed, still at: ${finalUrl}`);
        }
      } else {
        results.logout.error = 'Logout button not found';
        console.log('✗ Logout button not found on page');

        // Take screenshot showing entire page for debugging
        await page.screenshot({ path: path.join(screenshotDir, 'final-10-no-logout-button.png'), fullPage: true });
      }
    }

  } catch (error) {
    console.error('\n❌ Test failed with error:', error.message);
    results.globalError = error.message;

    // Take error screenshot
    try {
      await page.screenshot({ path: path.join(screenshotDir, 'final-error.png'), fullPage: true });
    } catch (e) {
      // Ignore screenshot errors
    }
  } finally {
    await browser.close();
  }

  // =========================
  // GENERATE REPORT
  // =========================
  console.log('\n\n' + '='.repeat(60));
  console.log('E2E TEST RESULTS SUMMARY');
  console.log('='.repeat(60));

  console.log('\n📝 Test Credentials:');
  console.log(`   Email: ${testEmail}`);
  console.log(`   Business: ${testBusinessName}`);

  console.log('\n✅ Successes:');
  if (results.registration.success) console.log('   ✓ Registration');
  if (results.login.success) console.log('   ✓ Login');
  if (results.dashboard.success) console.log('   ✓ Dashboard Access');
  if (results.products.success) console.log('   ✓ Products Page');
  if (results.recommendations.success) console.log('   ✓ Recommendations Page');
  if (results.settings.success) console.log('   ✓ Settings Page');
  if (results.logout.success) console.log('   ✓ Logout');

  console.log('\n❌ Failures:');
  if (!results.registration.success) console.log(`   ✗ Registration - ${results.registration.error || 'See error messages'}`);
  if (!results.login.success) console.log(`   ✗ Login - ${results.login.error || 'See error messages'}`);
  if (!results.dashboard.success) console.log(`   ✗ Dashboard - ${results.dashboard.error}`);
  if (!results.products.success) console.log(`   ✗ Products - ${results.products.error}`);
  if (!results.recommendations.success) console.log(`   ✗ Recommendations - ${results.recommendations.error}`);
  if (!results.settings.success) console.log(`   ✗ Settings - ${results.settings.error}`);
  if (!results.logout.success) console.log(`   ✗ Logout - ${results.logout.error || 'Failed'}`);

  console.log('\n' + '='.repeat(60));

  // Write detailed results to file
  fs.writeFileSync(
    path.join(screenshotDir, 'test-results-final.json'),
    JSON.stringify(results, null, 2)
  );

  console.log(`\n📁 Screenshots and detailed results saved to: ${screenshotDir}`);
  console.log(`📄 Detailed JSON report: test-results-final.json\n`);

  return results;
}

runE2ETest().catch(console.error);
