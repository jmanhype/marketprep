const playwright = require('playwright');
const fs = require('fs');
const path = require('path');

const screenshotDir = path.join(__dirname, 'e2e-test-screenshots');

// Ensure screenshot directory exists
if (!fs.existsSync(screenshotDir)) {
  fs.mkdirSync(screenshotDir, { recursive: true });
}

async function runE2ETest() {
  console.log('Starting MarketPrep Enhanced E2E Test...\n');

  const browser = await playwright.chromium.launch({ headless: false });
  const context = await browser.newContext();
  const page = await context.newPage();

  // Capture console logs
  const consoleLogs = [];
  page.on('console', msg => {
    consoleLogs.push({
      type: msg.type(),
      text: msg.text(),
      timestamp: new Date().toISOString()
    });
  });

  // Capture network errors
  const networkErrors = [];
  page.on('response', response => {
    if (response.status() >= 400) {
      networkErrors.push({
        url: response.url(),
        status: response.status(),
        statusText: response.statusText()
      });
    }
  });

  const results = {
    registration: { success: false, error: null, consoleLogs: [], networkErrors: [] },
    login: { success: false, error: null, consoleLogs: [], networkErrors: [] },
    dashboard: { success: false, error: null, features: [], content: '' },
    products: { success: false, error: null, features: [], content: '' },
    recommendations: { success: false, error: null, features: [], content: '' },
    settings: { success: false, error: null, features: [], content: '' },
    logout: { success: false, error: null }
  };

  try {
    // =========================
    // 1. REGISTRATION FLOW
    // =========================
    console.log('=== 1. TESTING REGISTRATION FLOW ===');
    await page.goto('http://localhost:3000/auth/register');
    await page.waitForLoadState('networkidle');
    await page.screenshot({ path: path.join(screenshotDir, '1-registration-page.png'), fullPage: true });
    console.log('✓ Registration page loaded');

    // Clear logs
    consoleLogs.length = 0;
    networkErrors.length = 0;

    // Fill out registration form
    await page.fill('input[placeholder="Your Farm or Business"]', 'E2E Test Farm');
    await page.fill('input[placeholder="vendor@example.com"]', 'e2etest@marketprep.test');
    const passwordFields = await page.locator('input[type="password"]').all();
    await passwordFields[0].fill('TestPass123');
    await passwordFields[1].fill('TestPass123');

    await page.screenshot({ path: path.join(screenshotDir, '2-registration-filled.png'), fullPage: true });
    console.log('✓ Registration form filled');

    // Submit registration and wait for response
    const [response] = await Promise.all([
      page.waitForResponse(response => response.url().includes('/api/auth/register') || response.url().includes('/register'), { timeout: 10000 }).catch(() => null),
      page.click('button:has-text("Create Account")')
    ]);

    await page.waitForTimeout(2000); // Wait for any UI updates

    // Check for error messages on page
    const errorMessage = await page.locator('.error, [role="alert"], .text-red-500, .text-red-600').allTextContents().catch(() => []);

    if (response) {
      console.log(`Registration API Response: ${response.status()} ${response.statusText()}`);
      try {
        const responseBody = await response.json().catch(() => null);
        console.log('Response body:', JSON.stringify(responseBody, null, 2));
        results.registration.responseBody = responseBody;
      } catch (e) {
        console.log('Could not parse response body');
      }
    }

    await page.screenshot({ path: path.join(screenshotDir, '3-after-registration.png'), fullPage: true });

    const currentUrl = page.url();
    console.log(`After registration, current URL: ${currentUrl}`);
    if (errorMessage.length > 0) {
      console.log(`Error messages found: ${errorMessage.join(', ')}`);
    }

    results.registration.redirectUrl = currentUrl;
    results.registration.errorMessages = errorMessage;
    results.registration.consoleLogs = [...consoleLogs];
    results.registration.networkErrors = [...networkErrors];
    results.registration.success = !currentUrl.includes('/register') && errorMessage.length === 0;

    // =========================
    // 2. LOGIN FLOW
    // =========================
    console.log('\n=== 2. TESTING LOGIN FLOW ===');

    // Try to login regardless of registration success
    await page.goto('http://localhost:3000/auth/login');
    await page.waitForLoadState('networkidle');

    consoleLogs.length = 0;
    networkErrors.length = 0;

    await page.fill('input[type="email"]', 'e2etest@marketprep.test');
    await page.fill('input[type="password"]', 'TestPass123');
    await page.screenshot({ path: path.join(screenshotDir, '4-login-filled.png'), fullPage: true });

    const [loginResponse] = await Promise.all([
      page.waitForResponse(response => response.url().includes('/api/auth/login') || response.url().includes('/login'), { timeout: 10000 }).catch(() => null),
      page.click('button:has-text("Sign In")')
    ]);

    await page.waitForTimeout(2000);

    if (loginResponse) {
      console.log(`Login API Response: ${loginResponse.status()} ${loginResponse.statusText()}`);
      try {
        const responseBody = await loginResponse.json().catch(() => null);
        console.log('Login response body:', JSON.stringify(responseBody, null, 2));
        results.login.responseBody = responseBody;
      } catch (e) {
        console.log('Could not parse login response body');
      }
    }

    const loginErrorMessage = await page.locator('.error, [role="alert"], .text-red-500, .text-red-600').allTextContents().catch(() => []);

    await page.screenshot({ path: path.join(screenshotDir, '5-after-login.png'), fullPage: true });

    console.log(`After login, current URL: ${page.url()}`);
    if (loginErrorMessage.length > 0) {
      console.log(`Login error messages: ${loginErrorMessage.join(', ')}`);
    }

    results.login.redirectUrl = page.url();
    results.login.errorMessages = loginErrorMessage;
    results.login.consoleLogs = [...consoleLogs];
    results.login.networkErrors = [...networkErrors];
    results.login.success = !page.url().includes('/auth/login') && loginErrorMessage.length === 0;

    // Only continue if we're logged in
    const isLoggedIn = !page.url().includes('/auth/');

    if (!isLoggedIn) {
      console.log('\n⚠️  Not logged in - skipping protected route tests');
      results.dashboard.error = 'Not authenticated';
      results.products.error = 'Not authenticated';
      results.recommendations.error = 'Not authenticated';
      results.settings.error = 'Not authenticated';
    } else {
      // =========================
      // 3. DASHBOARD ACCESS
      // =========================
      console.log('\n=== 3. TESTING DASHBOARD ACCESS ===');
      if (!page.url().includes('/dashboard')) {
        await page.goto('http://localhost:3000/dashboard');
        await page.waitForLoadState('networkidle');
      }
      await page.screenshot({ path: path.join(screenshotDir, '6-dashboard.png'), fullPage: true });

      const dashboardContent = await page.textContent('body');
      const dashboardTitle = await page.textContent('h1, h2').catch(() => 'No title found');
      const dashboardButtons = await page.locator('button').count();
      const dashboardLinks = await page.locator('a').count();

      results.dashboard.success = true;
      results.dashboard.content = dashboardContent.substring(0, 500);
      results.dashboard.features = [
        `Page title: ${dashboardTitle}`,
        `${dashboardButtons} buttons found`,
        `${dashboardLinks} links found`
      ];
      console.log(`✓ Dashboard loaded: ${dashboardTitle}`);

      // =========================
      // 4. PRODUCTS PAGE
      // =========================
      console.log('\n=== 4. TESTING PRODUCTS PAGE ===');
      try {
        await page.goto('http://localhost:3000/products');
        await page.waitForLoadState('networkidle');
        await page.screenshot({ path: path.join(screenshotDir, '7-products.png'), fullPage: true });

        const productsContent = await page.textContent('body');
        const productsTitle = await page.textContent('h1, h2').catch(() => 'No title found');
        const productButtons = await page.locator('button').count();

        results.products.success = true;
        results.products.content = productsContent.substring(0, 500);
        results.products.features = [
          `Page title: ${productsTitle}`,
          `${productButtons} buttons found`
        ];
        console.log(`✓ Products page loaded: ${productsTitle}`);
      } catch (error) {
        results.products.error = error.message;
        console.log(`✗ Products page error: ${error.message}`);
      }

      // =========================
      // 5. RECOMMENDATIONS PAGE
      // =========================
      console.log('\n=== 5. TESTING RECOMMENDATIONS PAGE ===');
      try {
        await page.goto('http://localhost:3000/recommendations');
        await page.waitForLoadState('networkidle');
        await page.screenshot({ path: path.join(screenshotDir, '8-recommendations.png'), fullPage: true });

        const recsContent = await page.textContent('body');
        const recsTitle = await page.textContent('h1, h2').catch(() => 'No title found');
        const recsButtons = await page.locator('button').count();

        results.recommendations.success = true;
        results.recommendations.content = recsContent.substring(0, 500);
        results.recommendations.features = [
          `Page title: ${recsTitle}`,
          `${recsButtons} buttons found`
        ];
        console.log(`✓ Recommendations page loaded: ${recsTitle}`);
      } catch (error) {
        results.recommendations.error = error.message;
        console.log(`✗ Recommendations page error: ${error.message}`);
      }

      // =========================
      // 6. SETTINGS PAGE
      // =========================
      console.log('\n=== 6. TESTING SETTINGS PAGE ===');
      try {
        await page.goto('http://localhost:3000/settings');
        await page.waitForLoadState('networkidle');
        await page.screenshot({ path: path.join(screenshotDir, '9-settings.png'), fullPage: true });

        const settingsContent = await page.textContent('body');
        const settingsTitle = await page.textContent('h1, h2').catch(() => 'No title found');
        const hasSquareIntegration = settingsContent.includes('Square') || settingsContent.includes('POS');

        results.settings.success = true;
        results.settings.content = settingsContent.substring(0, 500);
        results.settings.features = [
          `Page title: ${settingsTitle}`,
          `Square/POS integration visible: ${hasSquareIntegration}`
        ];
        console.log(`✓ Settings page loaded: ${settingsTitle}`);
      } catch (error) {
        results.settings.error = error.message;
        console.log(`✗ Settings page error: ${error.message}`);
      }

      // =========================
      // 7. LOGOUT TEST
      // =========================
      console.log('\n=== 7. TESTING LOGOUT ===');
      try {
        // Look for logout button
        const logoutButton = page.locator('button:has-text("Logout"), button:has-text("Log Out"), button:has-text("Sign Out"), a:has-text("Logout"), a:has-text("Log Out"), a:has-text("Sign Out")').first();

        if (await logoutButton.count() > 0) {
          await logoutButton.click();
          await page.waitForTimeout(2000);
          await page.screenshot({ path: path.join(screenshotDir, '10-after-logout.png'), fullPage: true });

          const finalUrl = page.url();
          results.logout.success = finalUrl.includes('/auth/login') || finalUrl.includes('/auth/register');
          results.logout.redirectUrl = finalUrl;
          console.log(`✓ Logout successful, redirected to: ${finalUrl}`);
        } else {
          results.logout.error = 'Logout button not found';
          console.log('✗ Logout button not found');
        }
      } catch (error) {
        results.logout.error = error.message;
        console.log(`✗ Logout error: ${error.message}`);
      }
    }

  } catch (error) {
    console.error('Test failed with error:', error);
    results.globalError = error.message;
  } finally {
    await browser.close();
  }

  // =========================
  // GENERATE REPORT
  // =========================
  console.log('\n\n=== E2E TEST RESULTS SUMMARY ===\n');
  console.log(JSON.stringify(results, null, 2));

  // Write results to file
  fs.writeFileSync(
    path.join(screenshotDir, 'test-results-enhanced.json'),
    JSON.stringify(results, null, 2)
  );

  console.log(`\n✓ Test complete! Screenshots and results saved to: ${screenshotDir}`);

  return results;
}

runE2ETest().catch(console.error);
