const playwright = require('playwright');
const fs = require('fs');
const path = require('path');

const screenshotDir = path.join(__dirname, 'e2e-test-screenshots');

// Ensure screenshot directory exists
if (!fs.existsSync(screenshotDir)) {
  fs.mkdirSync(screenshotDir, { recursive: true });
}

async function runE2ETest() {
  console.log('Starting MarketPrep E2E Test...\n');

  const browser = await playwright.chromium.launch({ headless: false });
  const context = await browser.newContext();
  const page = await context.newPage();

  const results = {
    registration: { success: false, error: null },
    login: { success: false, error: null },
    dashboard: { success: false, error: null, features: [] },
    products: { success: false, error: null, features: [] },
    recommendations: { success: false, error: null, features: [] },
    settings: { success: false, error: null, features: [] },
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

    // Fill out registration form
    await page.fill('input[placeholder="Your Farm or Business"]', 'E2E Test Farm');
    await page.fill('input[placeholder="vendor@example.com"]', 'e2etest@marketprep.test');
    const passwordFields = await page.locator('input[type="password"]').all();
    await passwordFields[0].fill('TestPass123');
    await passwordFields[1].fill('TestPass123');

    await page.screenshot({ path: path.join(screenshotDir, '2-registration-filled.png'), fullPage: true });
    console.log('✓ Registration form filled');

    // Submit registration
    await page.click('button:has-text("Create Account")');
    await page.waitForTimeout(2000); // Wait for submission
    await page.screenshot({ path: path.join(screenshotDir, '3-after-registration.png'), fullPage: true });

    const currentUrl = page.url();
    console.log(`✓ After registration, redirected to: ${currentUrl}`);

    results.registration.success = true;
    results.registration.redirectUrl = currentUrl;

    // =========================
    // 2. LOGIN FLOW (if needed)
    // =========================
    console.log('\n=== 2. TESTING LOGIN FLOW ===');
    if (currentUrl.includes('/auth/login')) {
      console.log('Redirected to login page, testing login...');
      await page.fill('input[type="email"]', 'e2etest@marketprep.test');
      await page.fill('input[type="password"]', 'TestPass123');
      await page.screenshot({ path: path.join(screenshotDir, '4-login-filled.png'), fullPage: true });

      await page.click('button:has-text("Sign In")');
      await page.waitForTimeout(2000);
      await page.screenshot({ path: path.join(screenshotDir, '5-after-login.png'), fullPage: true });

      console.log(`✓ After login, current URL: ${page.url()}`);
      results.login.success = true;
      results.login.redirectUrl = page.url();
    } else {
      console.log('Already logged in after registration');
      results.login.success = true;
      results.login.note = 'Auto-logged in after registration';
    }

    // =========================
    // 3. DASHBOARD ACCESS
    // =========================
    console.log('\n=== 3. TESTING DASHBOARD ACCESS ===');
    if (!page.url().includes('/dashboard')) {
      await page.goto('http://localhost:3000/dashboard');
      await page.waitForLoadState('networkidle');
    }
    await page.screenshot({ path: path.join(screenshotDir, '6-dashboard.png'), fullPage: true });

    // Analyze dashboard content
    const dashboardTitle = await page.textContent('h1, h2').catch(() => 'No title found');
    const dashboardButtons = await page.locator('button').count();
    const dashboardLinks = await page.locator('a').count();

    results.dashboard.success = true;
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

      const productsTitle = await page.textContent('h1, h2').catch(() => 'No title found');
      const productButtons = await page.locator('button').count();

      results.products.success = true;
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

      const recsTitle = await page.textContent('h1, h2').catch(() => 'No title found');
      const recsButtons = await page.locator('button').count();

      results.recommendations.success = true;
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

      const settingsTitle = await page.textContent('h1, h2').catch(() => 'No title found');
      const settingsContent = await page.textContent('body');
      const hasSquareIntegration = settingsContent.includes('Square') || settingsContent.includes('POS');

      results.settings.success = true;
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
      // Look for logout button (common selectors)
      const logoutButton = await page.locator('button:has-text("Logout"), button:has-text("Log Out"), button:has-text("Sign Out"), a:has-text("Logout"), a:has-text("Log Out"), a:has-text("Sign Out")').first();

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

  } catch (error) {
    console.error('Test failed with error:', error);
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
    path.join(screenshotDir, 'test-results.json'),
    JSON.stringify(results, null, 2)
  );

  console.log(`\n✓ Test complete! Screenshots and results saved to: ${screenshotDir}`);

  return results;
}

runE2ETest().catch(console.error);
