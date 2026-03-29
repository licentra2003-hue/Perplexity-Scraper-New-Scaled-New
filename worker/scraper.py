import asyncio
import json
import os
import random
import re
import urllib.parse
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import List, Optional

from playwright.async_api import Browser, Page, async_playwright
from playwright_stealth import Stealth


# ==================== DATA MODELS ====================

@dataclass
class SourceLink:
    text: str
    url: str
    raw_url: str = ""
    highlight_fragment: Optional[str] = None
    related_claim: str = field(default="General source")
    extraction_order: int = 0


@dataclass
class ScrapingResult:
    query: str
    ai_overview_text: str
    source_links: List[SourceLink]
    total_interactions: int
    success: bool
    timestamp: str
    error_message: Optional[str] = None


# ==================== LOCATION CONFIGURATION ====================

LOCATION_CONFIG = {
    'USA': {
        'locale': 'en-US',
        'timezone_id': 'America/New_York',
        'geolocation': {'latitude': 40.7128, 'longitude': -74.0060},
        'permissions': ['geolocation'],
        'extra_http_headers': {'Accept-Language': 'en-US,en;q=0.9'}
    },
    'India': {
        'locale': 'en-IN',
        'timezone_id': 'Asia/Kolkata',
        'geolocation': {'latitude': 12.9716, 'longitude': 77.5946},
        'permissions': ['geolocation'],
        'extra_http_headers': {'Accept-Language': 'en-IN,en;q=0.9'}
    },
    'UK': {
        'locale': 'en-GB',
        'timezone_id': 'Europe/London',
        'geolocation': {'latitude': 51.5074, 'longitude': -0.1278},
        'permissions': ['geolocation'],
        'extra_http_headers': {'Accept-Language': 'en-GB,en;q=0.9'}
    },
    'Germany': {
        'locale': 'de-DE',
        'timezone_id': 'Europe/Berlin',
        'geolocation': {'latitude': 52.5200, 'longitude': 13.4050},
        'permissions': ['geolocation'],
        'extra_http_headers': {'Accept-Language': 'de-DE,de;q=0.9'}
    },
    'France': {
        'locale': 'fr-FR',
        'timezone_id': 'Europe/Paris',
        'geolocation': {'latitude': 48.8566, 'longitude': 2.3522},
        'permissions': ['geolocation'],
        'extra_http_headers': {'Accept-Language': 'fr-FR,fr;q=0.9'}
    },
    'Japan': {
        'locale': 'ja-JP',
        'timezone_id': 'Asia/Tokyo',
        'geolocation': {'latitude': 35.6895, 'longitude': 139.6917},
        'permissions': ['geolocation'],
        'extra_http_headers': {'Accept-Language': 'ja-JP,ja;q=0.9'}
    },
    'Australia': {
        'locale': 'en-AU',
        'timezone_id': 'Australia/Sydney',
        'geolocation': {'latitude': -33.8688, 'longitude': 151.2093},
        'permissions': ['geolocation'],
        'extra_http_headers': {'Accept-Language': 'en-AU,en;q=0.9'}
    },
    'Mexico': {
        'locale': 'es-MX',
        'timezone_id': 'America/Mexico_City',
        'geolocation': {'latitude': 19.4326, 'longitude': -99.1332},
        'permissions': ['geolocation'],
        'extra_http_headers': {'Accept-Language': 'es-MX,es;q=0.9'}
    },
    'Indonesia': {
        'locale': 'id-ID',
        'timezone_id': 'Asia/Jakarta',
        'geolocation': {'latitude': -6.2088, 'longitude': 106.8456},
        'permissions': ['geolocation'],
        'extra_http_headers': {'Accept-Language': 'id-ID,id;q=0.9'}
    },
    'South Korea': {
        'locale': 'ko-KR',
        'timezone_id': 'Asia/Seoul',
        'geolocation': {'latitude': 37.5665, 'longitude': 126.9780},
        'permissions': ['geolocation'],
        'extra_http_headers': {'Accept-Language': 'ko-KR,ko;q=0.9'}
    },
    'Philippines': {
        'locale': 'en-PH',
        'timezone_id': 'Asia/Manila',
        'geolocation': {'latitude': 14.5995, 'longitude': 120.9842},
        'permissions': ['geolocation'],
        'extra_http_headers': {'Accept-Language': 'en-PH,en;q=0.9'}
    },
    'Spain': {
        'locale': 'es-ES',
        'timezone_id': 'Europe/Madrid',
        'geolocation': {'latitude': 40.4168, 'longitude': -3.7038},
        'permissions': ['geolocation'],
        'extra_http_headers': {'Accept-Language': 'es-ES,es;q=0.9'}
    },
    'Netherlands': {
        'locale': 'nl-NL',
        'timezone_id': 'Europe/Amsterdam',
        'geolocation': {'latitude': 52.3676, 'longitude': 4.9041},
        'permissions': ['geolocation'],
        'extra_http_headers': {'Accept-Language': 'nl-NL,nl;q=0.9'}
    },
    'Serbia': {
        'locale': 'sr-RS',
        'timezone_id': 'Europe/Belgrade',
        'geolocation': {'latitude': 44.7866, 'longitude': 20.4489},
        'permissions': ['geolocation'],
        'extra_http_headers': {'Accept-Language': 'sr-RS,sr;q=0.9'}
    },
    'Kenya': {
        'locale': 'en-KE',
        'timezone_id': 'Africa/Nairobi',
        'geolocation': {'latitude': -1.2921, 'longitude': 36.8219},
        'permissions': ['geolocation'],
        'extra_http_headers': {'Accept-Language': 'en-KE,en;q=0.9'}
    },
}


# ==================== BROWSER MANAGER ====================

class BrowserManager:
    def __init__(self):
        self.browser: Optional[Browser] = None
        self.playwright = None
        self.stealth = None
        self._lock = asyncio.Lock()

    async def start(self):
        async with self._lock:
            if self.browser is not None:
                return

            self.stealth = Stealth()
            self.playwright = await self.stealth.use_async(async_playwright()).__aenter__()

            proxy_server = os.environ.get("PROXY_SERVER")
            proxy_username = os.environ.get("PROXY_USERNAME")
            proxy_password = os.environ.get("PROXY_PASSWORD")

            proxy = None
            if proxy_server:
                proxy = {
                    "server": proxy_server,
                    "username": proxy_username,
                    "password": proxy_password,
                }

            self.browser = await self.playwright.chromium.launch(
                headless=True,
                proxy=proxy,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-accelerated-2d-canvas',
                    '--disable-gpu',
                    '--disable-blink-features=AutomationControlled',
                ]
            )

    async def stop(self):
        async with self._lock:
            try:
                if self.browser and self.browser.is_connected():
                    await self.browser.close()
            except Exception:
                pass
            self.browser = None

            try:
                if self.playwright:
                    await self.playwright.__aexit__(None, None, None)
            except Exception:
                pass
            self.playwright = None

    async def is_healthy(self) -> bool:
        return self.browser is not None and self.browser.is_connected()

    async def create_page(self, location: str, user_agent: str):
        """Create an isolated browser context and page for one scrape job."""
        if location not in LOCATION_CONFIG:
            location = "India"

        location_settings = LOCATION_CONFIG[location]

        context = await self.browser.new_context(
            user_agent=user_agent,
            viewport={'width': 1920, 'height': 1080},
            **location_settings
        )
        await context.grant_permissions(location_settings.get('permissions', []))
        page = await context.new_page()
        return page, context


# ==================== SCRAPER ====================

class PerplexityScraper:
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0",
    ]

    async def scrape(self, page: Page, query: str) -> ScrapingResult:
        timestamp = datetime.now().isoformat()

        try:
            await page.goto("https://www.perplexity.ai/", wait_until="domcontentloaded")
            await self._random_wait(2.0, 4.0)
            await self._handle_popups(page)
            await self._human_search(page, query)

            print(f"Waiting for full response — query: {query!r}")
            await self._wait_for_full_response(page, timeout_ms=60000)

            page_content = await page.locator("body").inner_text()
            if self._is_bot_detected(page_content):
                raise Exception("Bot detection or captcha encountered")

            full_ai_text, source_links = await self._extract_granular_content(page)

            return ScrapingResult(
                query=query,
                ai_overview_text=full_ai_text,
                source_links=source_links,
                total_interactions=len(source_links),
                success=bool(full_ai_text.strip()),
                timestamp=timestamp,
            )

        except Exception as e:
            print(f"Scraping error for query {query!r}: {e}")
            return ScrapingResult(
                query=query,
                ai_overview_text="",
                source_links=[],
                total_interactions=0,
                success=False,
                timestamp=timestamp,
                error_message=str(e),
            )

    async def _wait_for_full_response(self, page: Page, timeout_ms: int):
        try:
            related_section_header = page.locator('div.font-display:has-text("Related")')
            await related_section_header.first.wait_for(state="visible", timeout=timeout_ms)
            print("Full response generated (detected 'Related' section)")
        except Exception as e:
            print(f"Timed out waiting for full response: {e}. Proceeding with partial content.")

    async def _handle_popups(self, page: Page):
        try:
            selectors = [
                'button[aria-label="Close"]',
                'div[role="dialog"] button:has-text("No thanks")',
                '.modal-content button.close',
            ]
            for selector in selectors:
                btn = page.locator(selector).first
                if await btn.is_visible(timeout=1500):
                    await btn.click()
                    await self._random_wait(0.5, 1.0)
                    return
        except Exception:
            pass

    async def _human_search(self, page: Page, query: str):
        try:
            await page.wait_for_load_state('domcontentloaded')
            await self._random_wait(1.0, 2.0)

            search_box = page.locator("#ask-input")

            if await search_box.count() == 0 or not await search_box.is_visible(timeout=5000):
                for frame in page.frames:
                    box_in_frame = frame.locator("textarea[placeholder*='Ask anything']")
                    if await box_in_frame.count() > 0:
                        search_box = box_in_frame
                        break

            if not search_box or await search_box.count() == 0:
                raise Exception("Could not find search box")

            await search_box.focus()
            await self._random_wait(0.5, 1.0)
            await search_box.fill(query, timeout=5000)
            await self._random_wait(1.5, 3.0)
            await page.keyboard.press("Enter")

            try:
                await page.wait_for_url("**/search**", timeout=30000)
            except Exception:
                current_url = page.url
                if "/search" not in current_url:
                    raise

            try:
                await page.wait_for_selector('div[id^="markdown-content-"]', timeout=30000)
            except Exception:
                pass

        except Exception as e:
            current_url = page.url
            if current_url and "/search" in current_url:
                return
            await page.goto(
                f"https://www.perplexity.ai/search?q={urllib.parse.quote_plus(query)}",
                wait_until="domcontentloaded"
            )

    async def _extract_granular_content(self, page: Page):
        all_source_links = []
        full_text_parts = []
        processed_urls = set()
        extraction_order = 0

        # --- Step 1: Top source cards ---
        try:
            source_grid = page.locator('div.gap-sm.grid.grid-cols-3, div[class*="grid"][class*="grid-cols"]').first
            source_cards = source_grid.locator('div.min-w-0 > div > a[href][target="_blank"]')
            card_count = await source_cards.count()

            for i in range(card_count):
                card = source_cards.nth(i)
                try:
                    url = await card.get_attribute("href")
                    if not url:
                        continue
                    cleaned_url = self._clean_url(url)
                    if not cleaned_url or cleaned_url in processed_urls:
                        continue

                    domain_elem = card.locator('div.line-clamp-1.min-w-0.grow.break-all')
                    domain = ""
                    if await domain_elem.count() > 0:
                        domain = (await domain_elem.first.inner_text()).strip()

                    title_elem = card.locator('span.line-clamp-1, span[class*="line-clamp"]')
                    title = ""
                    if await title_elem.count() > 0:
                        title = (await title_elem.last.inner_text()).strip()

                    display_text = title if title else domain

                    if self._is_valid_source_link(cleaned_url, display_text):
                        extraction_order += 1
                        all_source_links.append(SourceLink(
                            text=display_text,
                            url=cleaned_url,
                            raw_url=url,
                            related_claim="Top source card",
                            extraction_order=extraction_order,
                        ))
                        processed_urls.add(cleaned_url)
                except Exception:
                    continue
        except Exception as e:
            print(f"Warning: could not extract source cards: {e}")

        # --- Step 2: Response text + inline citations ---
        try:
            response_container = page.locator('div[id^="markdown-content-"]').first
            all_elements = await response_container.locator("p, ul, ol, h2, h3, h4, li, td").all()
            processed_blocks = set()

            for elem in all_elements:
                try:
                    if not await elem.is_visible():
                        continue
                    elem_handle = await elem.element_handle()
                    if elem_handle:
                        cleaned_text = await elem_handle.evaluate('''
                            el => {
                                const clone = el.cloneNode(true);
                                clone.querySelectorAll('span.citation, span.citation-nbsp').forEach(c => c.remove());
                                return clone.innerText;
                            }
                        ''')
                        cleaned_text = self._clean_text_chunk(cleaned_text)
                        if cleaned_text and cleaned_text not in processed_blocks and len(cleaned_text) > 10:
                            full_text_parts.append(cleaned_text)
                            processed_blocks.add(cleaned_text)
                except Exception:
                    continue

            # Inline citations
            citation_spans = response_container.locator('span.citation.inline')
            citation_count = await citation_spans.count()

            for cite_idx in range(citation_count):
                citation_span = citation_spans.nth(cite_idx)
                try:
                    citation_link = citation_span.locator('a[href]').first
                    if await citation_link.count() == 0:
                        continue

                    url = await citation_link.get_attribute("href")
                    if not url:
                        continue

                    cleaned_url = self._clean_url(url)
                    if not cleaned_url or cleaned_url in processed_urls:
                        continue

                    domain_span = citation_link.locator('span[class*="overflow-hidden"]').first
                    domain_name = ""
                    if await domain_span.count() > 0:
                        domain_name = (await domain_span.inner_text()).strip()

                    plus_span = citation_link.locator('span.opacity-50')
                    plus_count = ""
                    if await plus_span.count() > 0:
                        plus_count = (await plus_span.inner_text()).strip()

                    display_text = f"{domain_name}{plus_count}".strip()

                    parent_elem = citation_span.locator('xpath=ancestor::p | ancestor::td | ancestor::li').first
                    context_text = "Inline citation"

                    if await parent_elem.count() > 0:
                        parent_text_handle = await parent_elem.element_handle()
                        if parent_text_handle:
                            context_text = await parent_text_handle.evaluate('''
                                (el, citationSpan) => {
                                    const clone = el.cloneNode(true);
                                    const citationHTML = citationSpan.outerHTML;
                                    const citations = clone.querySelectorAll('span.citation');
                                    let targetCitation = null;
                                    for (let cite of citations) {
                                        if (cite.outerHTML === citationHTML) { targetCitation = cite; break; }
                                    }
                                    if (targetCitation) {
                                        let textBefore = '';
                                        let node = clone.firstChild;
                                        while (node) {
                                            if (node === targetCitation) break;
                                            if (node.nodeType === Node.TEXT_NODE) textBefore += node.textContent;
                                            else if (node.nodeType === Node.ELEMENT_NODE && !node.classList.contains('citation'))
                                                textBefore += node.innerText || node.textContent;
                                            node = node.nextSibling;
                                        }
                                        textBefore = textBefore.trim();
                                        const sentences = textBefore.split(/[.!?]+/);
                                        if (sentences.length > 0) {
                                            const last = sentences[sentences.length - 1].trim();
                                            if (last.length > 20) return last;
                                        }
                                        return textBefore.slice(-200);
                                    }
                                    clone.querySelectorAll('span.citation').forEach(c => c.remove());
                                    return clone.innerText.trim();
                                }
                            ''', await citation_span.element_handle())
                            context_text = self._clean_text_chunk(context_text)
                            if not context_text or len(context_text) < 10:
                                full_parent_text = await parent_elem.evaluate('''
                                    el => {
                                        const clone = el.cloneNode(true);
                                        clone.querySelectorAll('span.citation').forEach(c => c.remove());
                                        return clone.innerText;
                                    }
                                ''')
                                context_text = self._clean_text_chunk(full_parent_text)[:300]

                    if self._is_valid_source_link(cleaned_url, display_text or domain_name):
                        extraction_order += 1
                        normalized = self._normalize_citation_text(display_text or domain_name or "Citation")
                        all_source_links.append(SourceLink(
                            text=normalized,
                            url=cleaned_url,
                            raw_url=url,
                            related_claim=context_text,
                            extraction_order=extraction_order,
                        ))
                        processed_urls.add(cleaned_url)
                except Exception:
                    continue

        except Exception as e:
            print(f"Error extracting response content: {e}")

        # --- Step 3: Table citations ---
        try:
            response_container = page.locator('div[id^="markdown-content-"]').first
            tables = response_container.locator('table')
            table_count = await tables.count()

            for table_idx in range(table_count):
                table = tables.nth(table_idx)
                cells_with_citations = table.locator('td:has(span.citation)')
                cell_count = await cells_with_citations.count()

                for cell_idx in range(cell_count):
                    cell = cells_with_citations.nth(cell_idx)
                    try:
                        cell_text = await cell.evaluate('''
                            el => {
                                const clone = el.cloneNode(true);
                                clone.querySelectorAll('span.citation').forEach(c => c.remove());
                                return clone.innerText;
                            }
                        ''')
                        cell_text = self._clean_text_chunk(cell_text)
                        cell_citations = cell.locator('span.citation.inline a[href]')
                        cite_count = await cell_citations.count()

                        for c_idx in range(cite_count):
                            cite_link = cell_citations.nth(c_idx)
                            try:
                                url = await cite_link.get_attribute("href")
                                if not url:
                                    continue
                                cleaned_url = self._clean_url(url)
                                if not cleaned_url or cleaned_url in processed_urls:
                                    continue

                                domain_span = cite_link.locator('span[class*="overflow-hidden"]').first
                                domain_name = ""
                                if await domain_span.count() > 0:
                                    domain_name = (await domain_span.inner_text()).strip()

                                plus_span = cite_link.locator('span.opacity-50')
                                plus_text = ""
                                if await plus_span.count() > 0:
                                    plus_text = (await plus_span.inner_text()).strip()

                                display_text = f"{domain_name}{plus_text}".strip()

                                if self._is_valid_source_link(cleaned_url, display_text):
                                    extraction_order += 1
                                    normalized = self._normalize_citation_text(display_text or domain_name)
                                    all_source_links.append(SourceLink(
                                        text=normalized,
                                        url=cleaned_url,
                                        raw_url=url,
                                        related_claim=f"Table citation: {cell_text[:150]}",
                                        extraction_order=extraction_order,
                                    ))
                                    processed_urls.add(cleaned_url)
                            except Exception:
                                continue
                    except Exception:
                        continue
        except Exception as e:
            print(f"Error scanning tables: {e}")

        full_ai_text = "\n\n".join(full_text_parts)
        print(f"Extraction complete — {len(all_source_links)} sources, {len(full_ai_text)} chars")
        return full_ai_text, all_source_links

    # ==================== HELPERS ====================

    def _normalize_citation_text(self, text: str) -> str:
        if not text:
            return ""
        match = re.match(r'(.+?)\s*\+(\d+)$', text)
        if match:
            base, count = match.groups()
            return f"{base.strip()} (+{count} sources)"
        return text.strip()

    def _clean_url(self, url: str) -> str:
        if not url:
            return ""
        parts = urllib.parse.urlparse(url)
        cleaned = urllib.parse.urlunparse(parts[:3] + ('', '', ''))
        return f"https://www.perplexity.ai{cleaned}" if cleaned.startswith("/") else cleaned

    def _is_valid_source_link(self, url: str, text: str) -> bool:
        if not url or not text.strip():
            return False
        url_lower = url.lower()
        if any(s in url_lower for s in ["javascript:", "mailto:", "tel:"]):
            return False
        return url_lower.startswith("http")

    def _clean_text_chunk(self, text: str) -> str:
        if not text:
            return ""
        text = re.sub(r'\[\d+\]', '', text)
        text = re.sub(r'\$\d+\.\d+', '', text)
        text = re.sub(r'buy now', '', text, flags=re.IGNORECASE)
        text = re.sub(r'[\u200B-\u200D\uFEFF]', '', text)
        text = re.sub(r'\s+([a-zA-Z0-9-]+\.[a-zA-Z]{2,})(\s*\+\d+)?\s*$', '', text)
        lines = [
            line.strip() for line in text.splitlines()
            if line.strip() and len(line.strip()) > 10
            and not re.match(r'^[a-zA-Z0-9-]+\.[a-zA-Z]{2,}$', line.strip())
        ]
        return "\n".join(lines).strip()

    def _is_bot_detected(self, page_text: str) -> bool:
        return any(p in page_text.lower() for p in ["verify you are human", "captcha", "are you a robot"])

    async def _random_wait(self, min_s: float, max_s: float):
        await asyncio.sleep(random.uniform(min_s, max_s))