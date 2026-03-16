import base64
import json
import os
import shutil
import time

from cryptography.hazmat.primitives import serialization
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError, Error as PlaywrightError

from powers.utils.config import Auth, Web
from powers.utils.logger import log

import pyotp

def get_otp_code() -> str:
    """Generate the current TOTP code for Microsoft 2FA using the shared secret."""
    totp = pyotp.TOTP(Auth.MICROSOFT_SECRET)
    return totp.now()

def initialize_playwright(headless: bool = True, no_cookie: bool = False):
    """Launch a Chromium context using storage_state for lightweight session management.

    Args:
        headless:  Run the browser without a visible window.
        no_cookie: Wipe the saved state.json before starting, forcing a
                   fresh login instead of reusing a cached session.

    Returns:
        Tuple ``(playwright_instance, browser, context, page)``.
    """
    if no_cookie and os.path.exists(Web.STATE_FILE):
        os.remove(Web.STATE_FILE)
        log.info("Cleared existing state.json.")

    p = sync_playwright().start()

    if not headless:
        log.info("Headless mode disabled – browser window is visible.")
    if no_cookie:
        log.info("Cookie reuse disabled – using a fresh browser context.")

    # Launch a standard browser instance (non-persistent)
    browser = p.chromium.launch(
        headless=headless,
        args=["--disable-features=WebAuthnRemoteDesktopSupport"]
    )

    context_kwargs = {
        "locale": "zh-CN",
        "timezone_id": "Asia/Hong_Kong",
        "viewport": {"width": 1280, "height": 800},
    }

    # Inject state if state.json exists and cookie reuse is allowed
    if not no_cookie and os.path.exists(Web.STATE_FILE):
        context_kwargs["storage_state"] = Web.STATE_FILE

    context = browser.new_context(**context_kwargs)
    page = context.new_page()

    return p, browser, context, page


def login(headless: bool = True, no_cookie: bool = False) -> tuple:
    """Authenticate against the HKUST AC portal and return a bearer token.

    Drives the full SSO flow (Microsoft login → Duo 2FA → portal redirect).

    Returns:
        ``(token, info)`` where *token* is the JWT string and *info* is the
        raw ``ggt_student`` object from the portal's localStorage.
    """
    log.info("Starting login...")
    p, browser, context, page = initialize_playwright(headless=headless, no_cookie=no_cookie)
    info = None
    token = None

    try:
        log.detail("Navigating to target URL...")
        page.goto(Web.TARGET_URL, wait_until="commit")

        # Wait until either we're logged in or the Microsoft login page is loaded

        # ac panel indicator
        login_success_indicator = page.locator(".ant-progress-circle-path").first
        # microsoft login indicator
        login_need_indicator = page.locator('.login-paginated-page')

        (login_success_indicator.or_(login_need_indicator)).wait_for(state='attached')


        if "w5.ab.ust.hk/njggt/app/" in page.url:
            log.info("Already logged in.")

        else:
            log.detail("Not logged in, starting full SSO flow...")

            submit_button = page.locator('#idSIButton9')
            
            # Select account / input email
            email_input = page.locator('input[name="loginfmt"]')
            email_element = page.locator(f"text={Auth.EMAIL}")
            email_input.or_(email_element).wait_for(state='attached')

            if email_element.count():
                email_element.click()
                log.detail(f"Selected account: {Auth.EMAIL}")
            else:
                email_input.fill(Auth.EMAIL)
                submit_button.click()
                log.detail(f"Filled email.")

            # Input password and submit
            password_input = page.locator('input[name="passwd"]')
            password_input.fill(Auth.PASSWORD)
            submit_button.click()
            log.detail("Filled password and submitted.")

            # Wait for 2FA prompt and input TOTP code
            otc_input = page.locator('input[name="otc"]')
            otc_submit = page.locator('#idSubmit_SAOTCC_Continue')

            data = {}
            def intercept_auth(route):
                nonlocal data
                response = route.fetch()
                data = response.json()
                route.fulfill(response=response)

            page.route("**/SAS/EndAuth", intercept_auth)

            otp_code = get_otp_code()
            otc_input.fill(otp_code)
            otc_submit.click()

            # Wait for the authentication response to be intercepted and processed
            with page.expect_response("**/SAS/EndAuth"): pass
            page.unroute("**/SAS/EndAuth")

            # Check if 2FA was successful based on the intercepted response
            if data['Success'] != True:
                raise RuntimeError(f"2FA failed – check the TOTP secret and system time. Reason: {data['Message']}.")

            log.detail(f"Filled TOTP code ({otp_code}) and submitted.")

            # Wait until ac portal loads / handle "stay signed in?" prompt
            log.detail("Waiting for portal to load or 'stay signed in' prompt...")

            stay_button = page.locator('input[name="DontShowAgain"]')
            login_success_indicator.or_(stay_button).wait_for(state='attached')

            if stay_button.count():
                # Click "Dont show again" + "Yes" to stay signed in
                stay_button.click()
                submit_button.click()
                log.detail("Clicked 'Dont show again' and 'Yes' on the stay-signed-in prompt.")

            page.wait_for_url(Web.TARGET_URL + "*", wait_until='commit')
            log.info("Login successful.")

        # Wait until the token is available in localStorage
        page.wait_for_function("() => window.localStorage.getItem('ggt_student') !== null")

        # Save state to file and return the state data dictionary directly
        state = context.storage_state(path=Web.STATE_FILE)
        log.detail(f"Session state saved to {Web.STATE_FILE}.")

        log.detail("Extracting token...")
        
        # ensure the ggt_student item is available before trying to read it
        page.wait_for_function("() => window.localStorage.getItem('ggt_student') !== null")
        
        raw_storage = page.evaluate("() => window.localStorage.getItem('ggt_student')")
        if not raw_storage:
            raise RuntimeError("Failed to find 'ggt_student' in localStorage.")
            
        info = json.loads(raw_storage)
        token = info.get("token", "")
        log.detail("Bearer token successfully extracted.")

    except PlaywrightTimeoutError:
        log.error("Timeout during login – check network or credentials.")
        raise
    except Exception as e:
        log.error(f"Error during login: {e}")
        raise

    finally:
        # Closing order: page -> context -> browser instance -> Playwright instance
        page.close()
        context.close()
        browser.close()
        p.stop()
        
    return token, info
            

if __name__ == "__main__":
    token, info = login(headless=True, no_cookie=False)
    print(f"\nToken: {token}")
    print(f"Info:  {info}")
