import asyncio
import logging
import os
import sys
import json
import argparse
import time
from datetime import datetime
from urllib.parse import urlparse, parse_qs
from typing import List, Dict, Any, Optional
from pathlib import Path
import re

# Constants for Adobe Analytics patterns
ADOBE_ANALYTICS_PATTERNS = [
    'omtrdc.net',           # Main Adobe Analytics domain
    'omniture.com',         # Legacy Adobe/Omniture domain
    'sc.omtrdc.net',        # Secure collect domain
    '2o7.net',              # Legacy Omniture domain
    'adobe.com/b/ss/',      # Adobe Analytics beacon path
    'adobe.io/aa/',         # Adobe Analytics API
    'demdex.net',           # Adobe Audience Manager
    'everesttech.net'       # Adobe Advertising Cloud
]
ANALYTICS_PATTERNS = ['analytics', 'tracking', 'metrics', 'omniture', 'sitecatalyst']
REQUIRED_PARAMETERS = ['v2', 'c23']  # Changed from events to URL parameters
ENVIRONMENT_KEYWORDS = {
    'production': ['prod', 'production'],
    'development': ['dev', 'development'], 
    'staging': ['stage', 'staging']
}


class AdobeAnalyticsSubscriptionTester:
    """
    All-in-one Adobe Analytics tester for subscription URLs
    """
    
    def __init__(self, subscription_file: str = "subscription.txt", verbose: bool = False):
        self.subscription_file = Path(subscription_file)
        self.results: List[Dict[str, Any]] = []
        self.verbose = verbose
        self._setup_logging()
        
    def _setup_logging(self) -> None:
        """Setup logging configuration"""
        level = logging.DEBUG if self.verbose else logging.INFO
        logging.basicConfig(
            level=level,
            format='[%(asctime)s] %(levelname)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        self.logger = logging.getLogger(__name__)
    
    def log(self, message: str, level: str = "INFO") -> None:
        """Log messages with appropriate level"""
        log_method = getattr(self.logger, level.lower(), self.logger.info)
        if level in ["ERROR", "RESULT"] or self.verbose:
            log_method(message)
    
    async def check_cookie_consent(self, page) -> bool:
        """Check if cookie consent popup is available and try to accept it"""
        cookie_consent_available = False
        
        # Cookie consent title patterns to look for
        consent_title_patterns = [
            "We need your consent to proceed",
            "We Care About Your Privacy", 
            "Wir benötigen Ihre Einwilligung, um fortzufahren",
            "Cookie Consent",
            "Privacy Settings",
            "Cookie Settings",
            "Manage Cookies",
            "We use cookies",
            "This website uses cookies",
            "Cookie Notice",
            "Privacy Notice",
            "Cookies and Privacy",
            "Your Privacy Choices"
        ]
        
        # Accept button text patterns - only accept/allow buttons
        accept_button_patterns = [
            "Accept All",
            "Accept all cookies", 
            "Accept All Cookies",
            "Alle akzeptieren",
            "Tout accepter",
            "Aceptar todo",
            "Accetta tutti",
            "Accept",
            "Agree",
            "Allow All",
            "Allow all cookies",
            "OK",
            "Continue"
        ]
        
        # Buttons to avoid clicking (settings/preferences)
        avoid_button_patterns = [
            "Cookie Preferences",
            "Cookie Settings", 
            "Manage Cookies",
            "Privacy Settings",
            "Customize",
            "Settings",
            "Preferences",
            "Choose",
            "Manage",
            "Reject",
            "Decline",
            "Deny"
        ]
        
        try:
            # Wait for page to load and any popups to appear
            await page.wait_for_timeout(1000)
            
            # First, check if any consent titles are present on the page
            try:
                page_text = await page.text_content('body')
                
                for pattern in consent_title_patterns:
                    if pattern.lower() in page_text.lower():
                        cookie_consent_available = True
                        self.log(f"Found cookie consent indicator: '{pattern}'", "DEBUG")
                        break
            except Exception as e:
                self.log(f"Error getting page text: {e}", "DEBUG")
                page_text = ""
            
            # If we found consent indicators, try to find and click accept button
            if cookie_consent_available:
                # First, try to find specific "Accept All" buttons
                accept_all_found = False
                
                accept_all_selectors = [
                    "button:has-text('Accept All')",
                    "button:has-text('Accept all cookies')",
                    "button:has-text('Accept All Cookies')",
                    "button:has-text('Alle akzeptieren')",
                    "a:has-text('Accept All')",
                    "a:has-text('Accept all cookies')",
                    "[type='button']:has-text('Accept All')",
                    "[type='submit']:has-text('Accept All')"
                ]
                
                for selector in accept_all_selectors:
                    try:
                        elements = await page.query_selector_all(selector)
                        for element in elements:
                            if await element.is_visible() and await element.is_enabled():
                                element_text = await element.text_content()
                                self.log(f"Found 'Accept All' button: '{element_text}'", "DEBUG")
                                try:
                                    await element.scroll_into_view_if_needed()
                                    await page.wait_for_timeout(200)
                                    await element.click()
                                    await page.wait_for_timeout(1000)
                                    accept_all_found = True
                                    break
                                except Exception as e:
                                    self.log(f"Failed to click Accept All button: {e}", "DEBUG")
                                    continue
                        if accept_all_found:
                            break
                    except Exception as e:
                        continue
                
                # If no specific "Accept All" button found, look for other accept buttons
                if not accept_all_found:
                    # Look for accept buttons with various selectors
                    accept_selectors = [
                        "button", "a", "input[type='button']", "input[type='submit']",
                        "[role='button']", ".button", ".btn"
                    ]
                    
                    button_found = False
                    for selector in accept_selectors:
                        try:
                            elements = await page.query_selector_all(selector)
                            for element in elements:
                                if await element.is_visible() and await element.is_enabled():
                                    button_text = await element.text_content()
                                    if button_text:
                                        button_text = button_text.strip()
                                        
                                        # First check if this is a button we should avoid
                                        should_avoid = False
                                        for avoid_pattern in avoid_button_patterns:
                                            if avoid_pattern.lower() in button_text.lower():
                                                should_avoid = True
                                                self.log(f"Skipping button: '{button_text}' (settings/preferences)", "DEBUG")
                                                break
                                        
                                        # If not a button to avoid, check if it's an accept button
                                        if not should_avoid:
                                            for accept_pattern in accept_button_patterns:
                                                if accept_pattern.lower() in button_text.lower():
                                                    self.log(f"Clicking accept button: '{button_text}'", "DEBUG")
                                                    try:
                                                        await element.scroll_into_view_if_needed()
                                                        await page.wait_for_timeout(200)
                                                        await element.click()
                                                        await page.wait_for_timeout(1000)
                                                        button_found = True
                                                        break
                                                    except Exception as click_error:
                                                        self.log(f"Failed to click button: {click_error}", "DEBUG")
                                                        continue
                                        if button_found:
                                            break
                            if button_found:
                                break
                        except Exception as selector_error:
                            continue
                    
                    if not button_found:
                        self.log("Cookie consent detected but no accept button found", "DEBUG")
            else:
                # Additional check with common cookie banner selectors
                cookie_selectors = [
                    "[id*='cookie']", "[class*='cookie']",
                    "[id*='consent']", "[class*='consent']", 
                    "[id*='gdpr']", "[class*='gdpr']",
                    "[id*='privacy']", "[class*='privacy']",
                    ".cookie-banner", "#cookie-banner",
                    ".consent-banner", "#consent-banner",
                    ".privacy-banner", "#privacy-banner"
                ]
                
                for selector in cookie_selectors:
                    try:
                        elements = await page.query_selector_all(selector)
                        for element in elements:
                            if await element.is_visible():
                                element_text = await element.text_content()
                                if element_text and element_text.strip():
                                    cookie_consent_available = True
                                    self.log(f"Found cookie banner element: {selector}", "DEBUG")
                                    break
                        if cookie_consent_available:
                            break
                    except:
                        continue
                        
        except Exception as e:
            self.log(f"Error checking cookie consent: {e}", "DEBUG")
        
        return cookie_consent_available
    
    def load_subscription_urls(self) -> List[str]:
        """Load URLs from subscription.txt file"""
        urls = []
        try:
            if not self.subscription_file.exists():
                self._create_sample_subscription_file()
                
            with self.subscription_file.open('r', encoding='utf-8') as file:
                for line_num, line in enumerate(file, 1):
                    url = line.strip()
                    if url and not url.startswith('#'):  # Skip empty lines and comments
                        # Normalize URL
                        normalized_url = self._normalize_url(url)
                        if normalized_url:
                            urls.append(normalized_url)
                            self.log(f"Loaded URL from line {line_num}: {normalized_url}", "DEBUG")
            
            if not urls:
                self.log("No URLs found in subscription.txt", "ERROR")
            else:
                self.log(f"Loaded {len(urls)} URLs from {self.subscription_file}", "INFO")
            
            return urls
        except Exception as e:
            self.log(f"Error reading {self.subscription_file}: {e}", "ERROR")
            return []
    
    def _create_sample_subscription_file(self) -> None:
        """Create a sample subscription file"""
        self.log(f"Creating sample {self.subscription_file} file", "INFO")
        sample_content = [
            "# Add your subscription URLs here, one per line",
            "# Example:",
            "# www.example.com", 
            "www.breastcancervision.com"
        ]
        with self.subscription_file.open('w', encoding='utf-8') as f:
            f.write('\n'.join(sample_content) + '\n')
    
    def _normalize_url(self, url: str) -> Optional[str]:
        """Normalize URL by adding protocol if missing"""
        if not url:
            return None
        # Add protocol if missing
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        return url

    async def test_adobe_analytics_for_url(self, page, url: str) -> Dict[str, Any]:
        """
        Test Adobe Analytics implementation for a specific URL
        """
        adobe_analytics = {}
        all_api = []
        errors = []

        # Create handler functions
        async def handle_response(response):
            try:
                api_info = {
                    'url': response.url,
                    'status': response.status,
                    'content_type': response.headers.get('content-type', ''),
                    'timestamp': datetime.now().isoformat()
                }
                all_api.append(api_info)
                
                # Check for Adobe Analytics requests
                if any(pattern in response.url for pattern in ADOBE_ANALYTICS_PATTERNS):
                    self.log(f"Found Adobe Analytics request for {url}: {response.url[:100]}...", "DEBUG")
                    self._extract_analytics_params(response.url, adobe_analytics)
                            
            except Exception as e:
                error_msg = f"Response handling error for {url}: {e}"
                errors.append(error_msg)
                self.log(error_msg, "ERROR")

        async def handle_request(request):
            # Log analytics-related requests with more detail
            if any(pattern in request.url.lower() for pattern in [p.lower() for p in ADOBE_ANALYTICS_PATTERNS] + ANALYTICS_PATTERNS):
                self.log(f"Analytics request for {url}: {request.method} {request.url[:150]}...", "DEBUG")
                # Also capture the request in the adobe_analytics dict for analysis
                if 'requests' not in adobe_analytics:
                    adobe_analytics['requests'] = []
                adobe_analytics['requests'].append({
                    'method': request.method,
                    'url': request.url,
                    'timestamp': datetime.now().isoformat()
                })

        try:
            # Create a fresh page context for this URL to ensure isolation
            context = page.context
            fresh_page = await context.new_page()
            
            # Set up event listeners on the fresh page
            fresh_page.on("response", handle_response)
            fresh_page.on("request", handle_request)

            # Navigate to the URL
            self.log(f"Navigating to: {url}", "INFO")
            await fresh_page.goto(url, wait_until="load", timeout=30000)
            
            # Check and handle cookie consent first
            self.log(f"Checking for cookie consent on: {url}", "DEBUG")
            cookie_consent_found = await self.check_cookie_consent(fresh_page)
            if cookie_consent_found:
                self.log(f"Cookie consent handled for: {url}", "INFO")
                # Wait a bit more after accepting cookies for analytics to initialize
                await fresh_page.wait_for_timeout(3000)
            
            # Wait for analytics to load
            await fresh_page.wait_for_timeout(5000)

            # Get page title for additional context
            page_title = await fresh_page.title()
            
            # Close the fresh page to clean up
            await fresh_page.close()
            
            # Analyze results
            return self.analyze_adobe_analytics(url, adobe_analytics, all_api, errors, page_title, cookie_consent_found)

        except Exception as e:
            error_msg = f"Error testing {url}: {e}"
            self.log(error_msg, "ERROR")
            return self._create_error_result(url, str(e), len(all_api))
    
    def _extract_analytics_params(self, response_url: str, adobe_analytics: dict) -> None:
        """Extract analytics parameters from response URL"""
        parsed_url = urlparse(response_url)
        query_params = parse_qs(parsed_url.query)
        
        if query_params:
            for key, values in query_params.items():
                adobe_analytics[key] = values[0] if values else ""
    
    def _create_error_result(self, url: str, error: str, api_count: int) -> Dict[str, Any]:
        """Create error result dictionary"""
        return {
            'url': url,
            'status': 'ERROR',
            'error': error,
            'adobe_analytics': {},
            'all_api_count': api_count,
            'timestamp': datetime.now().isoformat(),
            'page_title': 'Error loading page'
        }

    def analyze_adobe_analytics(self, url: str, adobe_analytics: Dict, all_api: List, 
                              errors: List, page_title: str, cookie_consent_found: bool = False) -> Dict[str, Any]:
        """
        Analyze Adobe Analytics data and determine test status
        """
        result = self._create_base_result(url, page_title, adobe_analytics, all_api, errors)
        result['cookie_consent_found'] = cookie_consent_found

        if not adobe_analytics:
            if cookie_consent_found:
                result.update(self._create_fail_result(
                    'Adobe Analytics not detected (after cookie consent)',
                    f'No Adobe Analytics data found even after accepting cookie consent. Checked {len(all_api)} network requests.',
                    'Verify Adobe Analytics implementation is correct and fires after cookie consent.'
                ))
                self.log(f"FAIL - No Adobe Analytics found for {url} (cookie consent was handled)", "RESULT")
            else:
                result.update(self._create_fail_result(
                    'Adobe Analytics not detected (no cookie consent found)',
                    f'No Adobe Analytics data found. No cookie consent detected. Checked {len(all_api)} network requests.',
                    'Check if site requires cookie consent or verify Adobe Analytics implementation.'
                ))
                self.log(f"FAIL - No Adobe Analytics found for {url} (no cookie consent detected)", "RESULT")
        else:
            self._analyze_analytics_data(url, adobe_analytics, result)

        return result
    
    def _create_base_result(self, url: str, page_title: str, adobe_analytics: Dict, 
                           all_api: List, errors: List) -> Dict[str, Any]:
        """Create base result dictionary"""
        return {
            'url': url,
            'page_title': page_title,
            'timestamp': datetime.now().isoformat(),
            'adobe_analytics': adobe_analytics,
            'all_api_count': len(all_api),
            'analytics_requests': len([api for api in all_api if 'omtrdc' in api.get('url', '')]),
            'errors': errors
        }
    
    def _create_fail_result(self, description: str, details: str, recommendation: str) -> Dict[str, str]:
        """Create fail result dictionary"""
        return {
            'status': 'FAIL',
            'description': description,
            'details': details,
            'recommendation': recommendation
        }
    
    def _analyze_analytics_data(self, url: str, adobe_analytics: Dict, result: Dict[str, Any]) -> None:
        """Analyze the actual analytics data"""
        # Extract key analytics parameters
        events = adobe_analytics.get('events', '')
        v2 = adobe_analytics.get('v2', '')
        c23 = adobe_analytics.get('c23', '')
        v61 = adobe_analytics.get('v61', '')
        page_name = adobe_analytics.get('pageName', '')
        server = adobe_analytics.get('server', '')

        # Check for required parameters (v2 and c23)
        has_required_params = all(adobe_analytics.get(param) for param in REQUIRED_PARAMETERS)
        
        # Check URL matching
        url_matches = any(param in url for param in [v2, c23, server] if param)

        if has_required_params and url_matches:
            env_status = self.check_environment_status(v61, url)
            self._update_result_with_env_status(result, env_status, events, v61, page_name, url)
        elif not has_required_params:
            result.update(self._create_fail_result(
                'Required Adobe Analytics parameters missing',
                f'Parameters found: v2={v2}, c23={c23}. Expected: {", ".join(REQUIRED_PARAMETERS)}',
                'Verify that required analytics URL parameters (v2 and c23) are configured.'
            ))
            self.log(f"FAIL - Missing required parameters for {url}: v2={v2}, c23={c23}", "RESULT")
        else:
            result.update(self._create_fail_result(
                'Adobe Analytics URL configuration issue',
                f'URL mismatch. v2: {v2}, c23: {c23}, server: {server}',
                'Check URL parameter configuration in Adobe Analytics.'
            ))
            self.log(f"FAIL - URL mismatch for {url}", "RESULT")
    
    def _update_result_with_env_status(self, result: Dict[str, Any], env_status: Dict[str, Any], 
                                     events: str, v61: str, page_name: str, url: str) -> None:
        """Update result based on environment status"""
        if env_status['valid']:
            result.update({
                'status': 'PASS',
                'description': 'Adobe Analytics working correctly',
                'details': f'URL Parameters verified (v2, c23), Environment: {v61}, Page: {page_name}',
                'environment': env_status['environment'],
                'recommendation': 'Analytics implementation is working correctly.'
            })
            self.log(f"PASS - Adobe Analytics working for {url}", "RESULT")
        else:
            result.update({
                'status': 'WARN',
                'description': 'Adobe Analytics URL parameters found but environment issue',
                'details': f'URL parameters (v2, c23) verified, but environment issue: {env_status["issue"]}. v61: {v61}',
                'environment': env_status['environment'],
                'recommendation': 'Check environment configuration in Adobe Analytics.'
            })
            self.log(f"WARN - Environment issue for {url}: {env_status['issue']}", "RESULT")

    def check_environment_status(self, v61: str, url: str) -> Dict[str, Any]:
        """Check if the analytics environment configuration is correct"""
        if not v61:
            return {
                'valid': True,  # Allow empty v61 for subscription sites
                'environment': 'Unknown',
                'issue': None
            }
        
        v61_lower = v61.lower()
        
        # Check against known environment keywords
        for env_name, keywords in ENVIRONMENT_KEYWORDS.items():
            if any(keyword in v61_lower for keyword in keywords):
                return {
                    'valid': True,
                    'environment': env_name.title(),
                    'issue': None
                }
        
        return {
            'valid': False,
            'environment': 'Unknown',
            'issue': f'Unrecognized environment: {v61}'
        }

    async def run_tests(self, headless: bool = True, browser_type: str = "chromium") -> bool:
        """Run Adobe Analytics tests for all URLs in subscription.txt"""
        urls = self.load_subscription_urls()
        
        if not urls:
            self.log("No URLs found to test", "ERROR")
            return False

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            self.log("Playwright not installed. Install with: pip install playwright", "ERROR")
            self.log("Then run: playwright install", "ERROR")
            return False

        async with async_playwright() as p:
            browser = await self._launch_browser(p, browser_type, headless)
            context = await browser.new_context()
            initial_page = await context.new_page()

            self.log(f"Testing {len(urls)} URLs using {browser_type} browser", "INFO")
            
            # Test each URL with proper isolation
            for i, url in enumerate(urls, 1):
                self.log(f"[{i}/{len(urls)}] Testing: {url}", "INFO")
                result = await self.test_adobe_analytics_for_url(initial_page, url)
                self.results.append(result)
                
                # Log immediate result
                status = result.get('status', 'UNKNOWN')
                description = result.get('description', 'No description')
                self.log(f"Result: {status} - {description}", "RESULT")

            await initial_page.close()
            await browser.close()
            return True
    
    async def _launch_browser(self, playwright, browser_type: str, headless: bool):
        """Launch browser based on type"""
        browsers = {
            "firefox": playwright.firefox,
            "webkit": playwright.webkit,
            "chromium": playwright.chromium
        }
        browser_launcher = browsers.get(browser_type, playwright.chromium)
        return await browser_launcher.launch(headless=headless)

    def save_results(self, output_file: str = "analytics_test_results.json") -> Optional[Dict[str, Any]]:
        """Save individual URL reports only - no summary or index files"""
        try:
            timestamp = datetime.now().strftime("%d-%m-%Y__%H_%M_%S")
            results_dir = Path("Adobe_Analytics_Results")
            results_dir.mkdir(exist_ok=True)
            
            individual_reports = []
            for result in self.results:
                url = result.get('url', 'unknown_url')
                clean_url = self._clean_url_for_filename(url)
                
                # Create URL-specific directory
                url_dir = results_dir / clean_url
                url_dir.mkdir(exist_ok=True)
                
                # Create individual report
                individual_filename = f"{clean_url}_adobe_analytics_{timestamp}.json"
                individual_path = url_dir / individual_filename
                
                individual_report = self._create_individual_report(result, clean_url)
                
                # Save individual report
                with individual_path.open('w', encoding='utf-8') as f:
                    json.dump(individual_report, f, indent=2)
                
                individual_reports.append({
                    'url': url,
                    'report_path': str(individual_path),
                    'status': result.get('status')
                })
                
                self.log(f"Individual report saved: {individual_path}", "INFO")
            
            self.log(f"Created {len(individual_reports)} individual URL reports", "INFO")
            
            return {
                'individual_reports': individual_reports,
                'results_directory': str(results_dir)
            }
            
        except Exception as e:
            self.log(f"Error saving results: {e}", "ERROR")
            return None
    
    def _clean_url_for_filename(self, url: str) -> str:
        """Clean URL for use as filename"""
        clean_url = re.sub(r'^https?://', '', url)
        clean_url = re.sub(r'[^\w\-_.]', '_', clean_url)
        return clean_url[:100]  # Limit length
    
    def _create_individual_report(self, result: Dict[str, Any], clean_url: str) -> Dict[str, Any]:
        """Create enhanced individual report structure"""
        analytics = result.get('adobe_analytics', {})
        
        individual_report = {
            'url_info': {
                'original_url': result.get('url'),
                'cleaned_url': clean_url,
                'test_timestamp': result.get('timestamp'),
                'page_title': result.get('page_title', 'Unknown')
            },
            'test_result': {
                'status': result.get('status'),
                'description': result.get('description'),
                'details': result.get('details'),
                'recommendation': result.get('recommendation'),
                'environment': result.get('environment', 'Unknown')
            },
            'analytics_data': {
                'adobe_analytics_found': bool(analytics),
                'analytics_parameters': analytics,
                'total_analytics_params': len(analytics),
                'analytics_requests_count': result.get('analytics_requests', 0),
                'total_api_requests': result.get('all_api_count', 0)
            },
            'technical_details': {
                'errors': result.get('errors', []),
                'has_errors': bool(result.get('errors')),
                'test_duration_info': 'Standard 5 second wait for analytics loading'
            }
        }
        
        # Add key analytics parameters if available
        if analytics:
            individual_report['key_analytics_params'] = {
                'events': analytics.get('events', ''),
                'page_name': analytics.get('pageName', ''),
                'server': analytics.get('server', ''),
                'environment_v61': analytics.get('v61', ''),
                'url_v2': analytics.get('v2', ''),
                'url_c23': analytics.get('c23', ''),
                'visitor_id': analytics.get('mid', ''),
                'currency': analytics.get('cc', ''),
                'screen_resolution': analytics.get('s', ''),
                'browser_info': analytics.get('v154', '')
            }
        
        return individual_report

    def print_summary(self) -> None:
        """Print a comprehensive summary of test results"""
        if not self.results:
            self.log("No results to summarize", "ERROR")
            return

        stats = self._calculate_test_stats()
        self._print_summary_header(stats)
        self._print_detailed_results()

    def _calculate_test_stats(self) -> Dict[str, int]:
        """Calculate test statistics"""
        total = len(self.results)
        stats = {
            'total': total,
            'passed': sum(1 for r in self.results if r.get('status') == 'PASS'),
            'failed': sum(1 for r in self.results if r.get('status') == 'FAIL'),
            'warnings': sum(1 for r in self.results if r.get('status') == 'WARN'),
            'errors': sum(1 for r in self.results if r.get('status') == 'ERROR')
        }
        stats['success_rate'] = (stats['passed'] / total * 100) if total > 0 else 0
        return stats

    def _print_summary_header(self, stats: Dict[str, int]) -> None:
        """Print summary header with statistics"""
        print(f"\n{'='*80}")
        print("ADOBE ANALYTICS TEST SUMMARY")
        print(f"{'='*80}")
        print(f"Total URLs tested: {stats['total']}")
        print(f"✓ Passed: {stats['passed']}")
        print(f"⚠ Warnings: {stats['warnings']}")
        print(f"✗ Failed: {stats['failed']}")
        print(f"⚡ Errors: {stats['errors']}")
        print(f"Success Rate: {stats['success_rate']:.1f}%")

    def _print_detailed_results(self) -> None:
        """Print detailed results for each URL"""
        print(f"\n{'='*80}")
        print("DETAILED RESULTS")
        print(f"{'='*80}")
        
        status_emojis = {'PASS': '✓', 'FAIL': '✗', 'WARN': '⚠', 'ERROR': '⚡'}
        
        for i, result in enumerate(self.results, 1):
            url = result.get('url', 'Unknown URL')
            status = result.get('status', 'UNKNOWN')
            description = result.get('description', 'No description')
            page_title = result.get('page_title', 'Unknown')
            
            status_emoji = status_emojis.get(status, '?')
            
            print(f"\n{i}. {status_emoji} {status} - {url}")
            print(f"   Page: {page_title}")
            print(f"   Result: {description}")
            
            if result.get('adobe_analytics'):
                analytics = result['adobe_analytics']
                events = analytics.get('events', 'None')
                page_name = analytics.get('pageName', 'None')
                environment = result.get('environment', 'Unknown')
                print(f"   Analytics: Events={events}, Page={page_name}, Env={environment}")
            else:
                print("   Analytics: No data found")
            
            if result.get('recommendation'):
                print(f"   Recommendation: {result['recommendation']}")
            
            print("-" * 80)

    def generate_html_report(self, output_file: str = "analytics_report.html") -> Optional[str]:
        """Generate an HTML report of the test results"""
        if not self.results:
            return None
            
        stats = self._calculate_test_stats()
        html_content = self._build_html_content(stats)
        
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(html_content)
            self.log(f"HTML report saved to {output_file}", "INFO")
            return output_file
        except Exception as e:
            self.log(f"Error generating HTML report: {e}", "ERROR")
            return None
    
    def _build_html_content(self, stats: Dict[str, int]) -> str:
        """Build HTML content for the report"""
        html_parts = [
            self._get_html_header(),
            self._get_html_summary(stats),
            self._get_html_detailed_results(),
            "</body>\n</html>"
        ]
        return ''.join(html_parts)
    
    def _get_html_header(self) -> str:
        """Get HTML header section"""
        return f"""<!DOCTYPE html>
<html>
<head>
    <title>Adobe Analytics Test Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .header {{ background-color: #f4f4f4; padding: 20px; border-radius: 5px; }}
        .summary {{ display: flex; gap: 20px; margin: 20px 0; }}
        .metric {{ background-color: #e9ecef; padding: 15px; border-radius: 5px; text-align: center; }}
        .metric h3 {{ margin: 0; color: #495057; }}
        .metric .number {{ font-size: 24px; font-weight: bold; }}
        .pass {{ color: #28a745; }}
        .fail {{ color: #dc3545; }}
        .warn {{ color: #ffc107; }}
        .error {{ color: #6c757d; }}
        .result-item {{ border: 1px solid #ddd; margin: 10px 0; padding: 15px; border-radius: 5px; }}
        .result-item.PASS {{ border-left: 5px solid #28a745; }}
        .result-item.FAIL {{ border-left: 5px solid #dc3545; }}
        .result-item.WARN {{ border-left: 5px solid #ffc107; }}
        .result-item.ERROR {{ border-left: 5px solid #6c757d; }}
        .analytics-data {{ background-color: #f8f9fa; padding: 10px; border-radius: 3px; margin-top: 10px; }}
        .timestamp {{ color: #6c757d; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Adobe Analytics Test Report</h1>
        <p class="timestamp">Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </div>
"""
    
    def _get_html_summary(self, stats: Dict[str, int]) -> str:
        """Get HTML summary section"""
        return f"""    <div class="summary">
        <div class="metric">
            <h3>Total Tests</h3>
            <div class="number">{stats['total']}</div>
        </div>
        <div class="metric">
            <h3>Passed</h3>
            <div class="number pass">{stats['passed']}</div>
        </div>
        <div class="metric">
            <h3>Failed</h3>
            <div class="number fail">{stats['failed']}</div>
        </div>
        <div class="metric">
            <h3>Warnings</h3>
            <div class="number warn">{stats['warnings']}</div>
        </div>
        <div class="metric">
            <h3>Errors</h3>
            <div class="number error">{stats['errors']}</div>
        </div>
    </div>
    
    <h2>Detailed Results</h2>
"""
    
    def _get_html_detailed_results(self) -> str:
        """Get HTML detailed results section"""
        html_parts = []
        for i, result in enumerate(self.results, 1):
            status = result.get('status', 'UNKNOWN')
            url = result.get('url', 'Unknown')
            page_title = result.get('page_title', 'Unknown')
            description = result.get('description', 'No description')
            analytics = result.get('adobe_analytics', {})
            
            html_parts.append(f"""    <div class="result-item {status}">
        <h3>{i}. {url}</h3>
        <p><strong>Status:</strong> <span class="{status.lower()}">{status}</span></p>
        <p><strong>Page Title:</strong> {page_title}</p>
        <p><strong>Description:</strong> {description}</p>
""")
            
            if analytics:
                events = analytics.get('events', 'None')
                page_name = analytics.get('pageName', 'None')
                v61 = analytics.get('v61', 'None')
                
                html_parts.append(f"""        <div class="analytics-data">
            <strong>Analytics Data:</strong><br>
            Events: {events}<br>
            Page Name: {page_name}<br>
            Environment (v61): {v61}<br>
            Total Parameters: {len(analytics)}
        </div>
""")
            
            if result.get('recommendation'):
                html_parts.append(f"        <p><strong>Recommendation:</strong> {result['recommendation']}</p>\n")
            
            html_parts.append("    </div>\n")
        
        return ''.join(html_parts)


async def main():
    """Main function to run the Adobe Analytics tests"""
    parser = argparse.ArgumentParser(description='Adobe Analytics Subscription Tester')
    parser.add_argument('--subscription-file', '-f', default='subscription.txt',
                       help='Path to subscription file (default: subscription.txt)')
    parser.add_argument('--output', '-o', default='analytics_test_results.json',
                       help='Output file for results (default: analytics_test_results.json)')
    parser.add_argument('--html-report', action='store_true',
                       help='Generate HTML report')
    parser.add_argument('--browser', choices=['chromium', 'firefox', 'webkit'], 
                       default='chromium', help='Browser to use for testing')
    parser.add_argument('--headless', action='store_true', default=True,
                       help='Run browser in headless mode (default: True)')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose logging')
    
    args = parser.parse_args()
    
    tester = AdobeAnalyticsSubscriptionTester(args.subscription_file, args.verbose)
    
    # Run the tests
    success = await tester.run_tests(headless=args.headless, browser_type=args.browser)
    
    if success:
        # Print summary
        tester.print_summary()
        
        # Save results
        saved_results = tester.save_results(args.output)
        
        if saved_results:
            _print_files_created_summary(saved_results)
        
        # Generate HTML report if requested
        if args.html_report:
            html_file = tester.generate_html_report()
            if html_file:
                print(f"HTML Report: {html_file}")
        
        print(f"\n{'='*60}")
        print("TESTING COMPLETE")
        print(f"{'='*60}")
        if args.verbose:
            print("Individual URL reports saved in Results/URL/ directories")
            if args.html_report:
                print("HTML report: analytics_report.html")
    else:
        print("Testing failed. Please check the logs above.")
        sys.exit(1)


def _print_files_created_summary(saved_results: Dict[str, Any]) -> None:
    """Print summary of created files"""
    print(f"\n{'='*60}")
    print("FILES CREATED")
    print(f"{'='*60}")
    print(f"Results Directory: {saved_results['results_directory']}")
    print(f"Individual Reports: {len(saved_results['individual_reports'])}")
    
    print("\nIndividual URL Reports:")
    status_emojis = {'PASS': '✓', 'FAIL': '✗', 'WARN': '⚠', 'ERROR': '⚡'}
    for report in saved_results['individual_reports']:
        status_emoji = status_emojis.get(report['status'], '?')
        print(f"  {status_emoji} {report['url']}")
        print(f"    └─ {report['report_path']}")


def _check_playwright_installation() -> bool:
    """Check if playwright is installed and available"""
    try:
        from playwright.async_api import async_playwright
        return True
    except ImportError:
        print("❌ Error: playwright not installed.")
        print("Please install it using:")
        print("  pip install playwright")
        print("  playwright install")
        print("\nAlternatively, run:")
        print("  pip install playwright==1.48.0")
        print("  python -m playwright install")
        return False


if __name__ == "__main__":
    if not _check_playwright_installation():
        sys.exit(1)
    
    print("Adobe Analytics Subscription Tester - Optimized Version")
    print("=" * 60)
    
    # Run the tests
    asyncio.run(main())
