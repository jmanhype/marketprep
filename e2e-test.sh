#!/bin/bash
# E2E Test Script for MarketPrep

# Navigate to register page
echo "1. Navigating to registration page..."
echo "http://localhost:3000/auth/register" | director mcp call-tool browser-mcp-automation browser_navigate

# Take screenshot
echo "2. Taking screenshot of registration page..."
echo "" | director mcp call-tool browser-mcp-automation browser_screenshot > /tmp/screenshot1.txt

# Fill business name
echo "3. Filling in business name..."
printf "Business Name field\ns2e28\nE2E Test Farm\nfalse\n" | director mcp call-tool browser-mcp-automation browser_type

# Fill email
echo "4. Filling in email..."
printf "Email field\ns2e33\ne2etest@marketprep.test\nfalse\n" | director mcp call-tool browser-mcp-automation browser_type

# Fill password
echo "5. Filling in password..."
printf "Password field\ns2e37\nTestPass123\nfalse\n" | director mcp call-tool browser-mcp-automation browser_type

# Fill confirm password
echo "6. Filling in confirm password..."
printf "Confirm Password field\ns2e43\nTestPass123\nfalse\n" | director mcp call-tool browser-mcp-automation browser_type

# Take screenshot before submit
echo "7. Taking screenshot before submit..."
echo "" | director mcp call-tool browser-mcp-automation browser_screenshot > /tmp/screenshot2.txt

# Click create account button
echo "8. Clicking Create Account button..."
printf "Create Account button\ns2e45\n" | director mcp call-tool browser-mcp-automation browser_click

# Wait and take screenshot after submit
sleep 2
echo "9. Taking screenshot after registration..."
echo "" | director mcp call-tool browser-mcp-automation browser_screenshot > /tmp/screenshot3.txt

echo "Registration test complete!"
