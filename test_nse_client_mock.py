"""Mock-based tests to verify requesting flows and edge cases in nse_client.py."""

import sys
import unittest
from unittest.mock import MagicMock, patch

# Mock dependencies to prevent ModuleNotFoundError and allow static verification of logic
mock_curl_cffi = MagicMock()
mock_playwright = MagicMock()

sys.modules['curl_cffi'] = mock_curl_cffi
sys.modules['curl_cffi.requests'] = mock_curl_cffi.requests
sys.modules['playwright'] = mock_playwright
sys.modules['playwright.sync_api'] = mock_playwright.sync_api

# Import the class under test
from nse_client import NSEClient, NSEClientError


class TestNSEClientFlows(unittest.TestCase):

    def setUp(self):
        # Create a fresh client and clean up mock states
        self.client = NSEClient()
        mock_curl_cffi.reset_mock()
        mock_playwright.reset_mock()

    def test_initialize_session_falls_back_on_failure(self):
        """If curl_cffi startup fails, initialize_session should try Playwright."""
        with patch.object(self.client, '_initialize_curl_cffi_session', return_value=False) as mock_curl_init, \
             patch.object(self.client, '_initialize_playwright_session', return_value=True) as mock_pw_init:
            
            result = self.client.initialize_session()
            
            self.assertTrue(result)
            mock_curl_init.assert_called_once()
            mock_pw_init.assert_called_once()
            self.assertEqual(self.client.mode, "playwright")

    def test_initialize_session_returns_false_if_both_strategies_fail(self):
        """Startup should fail only after both request strategies fail."""
        with patch.object(self.client, '_initialize_curl_cffi_session', return_value=False) as mock_curl_init, \
             patch.object(self.client, '_initialize_playwright_session', return_value=False) as mock_pw_init:

            result = self.client.initialize_session()

            self.assertFalse(result)
            mock_curl_init.assert_called_once()
            mock_pw_init.assert_called_once()
            self.assertEqual(self.client.mode, "playwright")

    def test_curl_cookie_names_support_string_iteration(self):
        """curl_cffi may iterate cookies as names, not cookie objects."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session.cookies = ["_abck", "ak_bmsc", "bm_sz"]

        with patch("nse_client.curl_requests") as mock_curl_requests:
            mock_curl_requests.Session.return_value = mock_session

            result = self.client._initialize_curl_cffi_session()

            self.assertTrue(result)
            self.assertTrue(self.client._session_initialized)

    def test_request_with_retry_last_attempt_switch_and_execute(self):
        """Test that if curl_cffi fails on the final attempt in _request_with_retry,
        the mode is switched to playwright, and the playwright fetch IS executed for this call immediately.
        """
        # Force curl_cffi mode
        self.client.mode = "curl_cffi"
        self.client._session_initialized = True
        
        # Mock session.get to raise an exception
        self.client.session = MagicMock()
        self.client.session.get.side_effect = Exception("Connection error")
        
        with patch.object(self.client, '_fetch_with_playwright') as mock_pw_fetch:
            mock_pw_fetch.return_value = [{"symbol": "TEST"}]
            # We call a method that uses _request_with_retry
            result = self.client.get_current_issues()
            
            # Verify result is fetched successfully from playwright
            self.assertEqual(result, [{"symbol": "TEST"}])
            # Verify the mode switched to playwright
            self.assertEqual(self.client.mode, "playwright")
            # Verify playwright fetch was called immediately
            mock_pw_fetch.assert_called_once()

    def test_missing_dependencies_graceful_failures(self):
        """Test that if curl_cffi or playwright is missing, they are handled gracefully."""
        # 1. Test curl_requests is None
        with patch('nse_client.curl_requests', None):
            self.assertFalse(self.client._initialize_curl_cffi_session())
            
            # Test that requesting transitions to playwright and fails if playwright is also None
            with patch('nse_client.sync_playwright', None):
                with self.assertRaises(NSEClientError):
                    self.client.get_current_issues()
                    
        # 2. Test sync_playwright is None
        with patch('nse_client.sync_playwright', None):
            self.assertFalse(self.client._initialize_playwright_session())
            with self.assertRaises(NSEClientError):
                self.client._fetch_with_playwright("http://test.com")

    def test_playwright_session_initialization_bypass(self):
        """Test that if self._page is open, _initialize_playwright_session returns True
        and sets _session_initialized=True immediately without actually navigating to main page
        or re-verifying cookies, even if session was marked unitialized.
        """
        # Setup page that is NOT closed
        mock_page = MagicMock()
        mock_page.is_closed.return_value = False
        self.client._page = mock_page
        self.client._session_initialized = False
        
        with patch('nse_client.sync_playwright') as mock_sync_pw:
            result = self.client._initialize_playwright_session()
            
            self.assertTrue(result)
            self.assertTrue(self.client._session_initialized)
            # Ensure it shortcut-returned and did NOT call start or launch new browser
            mock_sync_pw.assert_not_called()
            mock_page.goto.assert_not_called()

    def test_playwright_cleanup_on_non_200_status(self):
        """Test that if _initialize_playwright_session gets a non-200 status code,
        it returns False and closes browser resources.
        """
        self.client._page = None
        self.client._browser = MagicMock()
        self.client._context = MagicMock()
        
        mock_response = MagicMock()
        mock_response.status = 502  # Bad Gateway
        
        mock_page = MagicMock()
        mock_page.goto.return_value = mock_response
        self.client._context.new_page.return_value = mock_page
        
        with patch.object(self.client, '_close_playwright') as mock_close:
            # Inject playwright mock
            mock_pw_instance = MagicMock()
            mock_pw_instance.chromium.launch.return_value = self.client._browser
            self.client._browser.new_context.return_value = self.client._context
            
            with patch('nse_client.sync_playwright', return_value=MagicMock(start=MagicMock(return_value=mock_pw_instance))):
                result = self.client._initialize_playwright_session()
                
                self.assertFalse(result)
                self.assertEqual(mock_close.call_count, 2)


if __name__ == '__main__':
    unittest.main()
