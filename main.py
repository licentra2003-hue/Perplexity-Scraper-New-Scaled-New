
# Final API ready
import asyncio
import json
import os
import random
import re
import urllib.parse
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import List, Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from playwright.async_api import Browser, Page, async_playwright
from playwright_stealth import Stealth
from pydantic import BaseModel, Field

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


# ==================== PYDANTIC MODELS ====================

class ScrapeRequest(BaseModel):
    query: str = Field(..., description="Search query to scrape from Perplexity AI")
    location: str = Field(default="India", description="Location setting: 'India' or 'USA'")
    save_files: bool = Field(default=False, description="Whether to save results to files")

    class Config:
        json_schema_extra = {
            "example": {
                "query": "best tender management software",
                "location": "India",
                "save_files": False
            }
        }


class SourceLinkResponse(BaseModel):
    text: str
    url: str
    raw_url: str
    highlight_fragment: Optional[str] = None
    related_claim: str
    extraction_order: int


class ScrapeResponse(BaseModel):
    query: str
    ai_overview_text: str
    source_links: List[SourceLinkResponse]
    total_interactions: int
    success: bool
    timestamp: str
    error_message: Optional[str] = None


# # ==================== LOCATION CONFIGURATION ====================

# LOCATION_CONFIG = {
#     'India': {
#         'locale': 'en-IN',
#         'timezone_id': 'Asia/Kolkata',
#         'geolocation': {'latitude': 12.9716, 'longitude': 77.5946},
#         'permissions': ['geolocation'],
#         'extra_http_headers': {'Accept-Language': 'en-IN,en;q=0.9'}
#     },
#     'USA': {
#         'locale': 'en-US',
#         'timezone_id': 'America/New_York',
#         'geolocation': {'latitude': 40.7128, 'longitude': -74.0060},
#         'permissions': ['geolocation'],
#         'extra_http_headers': {'Accept-Language': 'en-US,en;q=0.9'}
#     }
# }

# ==================== LOCATION CONFIGURATION ====================

LOCATION_CONFIG = {
    # --- North America ---
    'USA': {
        'locale': 'en-US',
        'timezone_id': 'America/New_York',
        'geolocation': {'latitude': 40.7128, 'longitude': -74.0060}, # New York
        'permissions': ['geolocation'],
        'extra_http_headers': {'Accept-Language': 'en-US,en;q=0.9'}
    },
    'Mexico': {
        'locale': 'es-MX',
        'timezone_id': 'America/Mexico_City',
        'geolocation': {'latitude': 19.4326, 'longitude': -99.1332}, # Mexico City
        'permissions': ['geolocation'],
        'extra_http_headers': {'Accept-Language': 'es-MX,es;q=0.9'}
    },

    # --- Asia ---
    'India': {
        'locale': 'en-IN',
        'timezone_id': 'Asia/Kolkata',
        'geolocation': {'latitude': 12.9716, 'longitude': 77.5946}, # Bangalore
        'permissions': ['geolocation'],
        'extra_http_headers': {'Accept-Language': 'en-IN,en;q=0.9'}
    },
    'Indonesia': {
        'locale': 'id-ID',
        'timezone_id': 'Asia/Jakarta',
        'geolocation': {'latitude': -6.2088, 'longitude': 106.8456}, # Jakarta
        'permissions': ['geolocation'],
        'extra_http_headers': {'Accept-Language': 'id-ID,id;q=0.9'}
    },
    'Japan': {
        'locale': 'ja-JP',
        'timezone_id': 'Asia/Tokyo',
        'geolocation': {'latitude': 35.6895, 'longitude': 139.6917}, # Tokyo
        'permissions': ['geolocation'],
        'extra_http_headers': {'Accept-Language': 'ja-JP,ja;q=0.9'}
    },
    'South Korea': {
        'locale': 'ko-KR',
        'timezone_id': 'Asia/Seoul',
        'geolocation': {'latitude': 37.5665, 'longitude': 126.9780}, # Seoul
        'permissions': ['geolocation'],
        'extra_http_headers': {'Accept-Language': 'ko-KR,ko;q=0.9'}
    },
    'Philippines': {
        'locale': 'en-PH',
        'timezone_id': 'Asia/Manila',
        'geolocation': {'latitude': 14.5995, 'longitude': 120.9842}, # Manila
        'permissions': ['geolocation'],
        'extra_http_headers': {'Accept-Language': 'en-PH,en;q=0.9'}
    },

    # --- Europe ---
    'Germany': {
        'locale': 'de-DE',
        'timezone_id': 'Europe/Berlin',
        'geolocation': {'latitude': 52.5200, 'longitude': 13.4050}, # Berlin
        'permissions': ['geolocation'],
        'extra_http_headers': {'Accept-Language': 'de-DE,de;q=0.9'}
    },
    'UK': {
        'locale': 'en-GB',
        'timezone_id': 'Europe/London',
        'geolocation': {'latitude': 51.5074, 'longitude': -0.1278}, # London
        'permissions': ['geolocation'],
        'extra_http_headers': {'Accept-Language': 'en-GB,en;q=0.9'}
    },
    'France': {
        'locale': 'fr-FR',
        'timezone_id': 'Europe/Paris',
        'geolocation': {'latitude': 48.8566, 'longitude': 2.3522}, # Paris
        'permissions': ['geolocation'],
        'extra_http_headers': {'Accept-Language': 'fr-FR,fr;q=0.9'}
    },
    'Spain': {
        'locale': 'es-ES',
        'timezone_id': 'Europe/Madrid',
        'geolocation': {'latitude': 40.4168, 'longitude': -3.7038}, # Madrid
        'permissions': ['geolocation'],
        'extra_http_headers': {'Accept-Language': 'es-ES,es;q=0.9'}
    },
    'Netherlands': {
        'locale': 'nl-NL',
        'timezone_id': 'Europe/Amsterdam',
        'geolocation': {'latitude': 52.3676, 'longitude': 4.9041}, # Amsterdam
        'permissions': ['geolocation'],
        'extra_http_headers': {'Accept-Language': 'nl-NL,nl;q=0.9'}
    },
    'Serbia': {
        'locale': 'sr-RS',
        'timezone_id': 'Europe/Belgrade',
        'geolocation': {'latitude': 44.7866, 'longitude': 20.4489}, # Belgrade
        'permissions': ['geolocation'],
        'extra_http_headers': {'Accept-Language': 'sr-RS,sr;q=0.9'}
    },

    # --- Africa ---
    'Kenya': {
        'locale': 'en-KE',
        'timezone_id': 'Africa/Nairobi',
        'geolocation': {'latitude': -1.2921, 'longitude': 36.8219}, # Nairobi
        'permissions': ['geolocation'],
        'extra_http_headers': {'Accept-Language': 'en-KE,en;q=0.9'}
    }
}


# ==================== SCRAPER CLASS ====================

class PerplexityScraper:
    def __init__(self):
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0",
        ]
        self.log_messages = []

    async def scrape(self, page: Page, query: str, save_files: bool = False) -> ScrapingResult:
        timestamp = datetime.now().isoformat()
        self.log_messages = [f"VERBOSE LOG FOR QUERY: '{query}' at {timestamp}"]
        self.log_messages.append("✓ Playwright_stealth applied via global context manager.")

        try:
            await page.goto("https://www.perplexity.ai/", wait_until="domcontentloaded")
            await self._random_wait(2.0, 4.0)
            await self._handle_popups(page)
            await self._human_search(page, query)

            print("Waiting for full search results to generate...")
            await self._wait_for_full_response(page, timeout_ms=60000) 

            page_content = await page.locator("body").inner_text()
            if self._is_bot_detected(page_content):
                raise Exception("Bot detection or captcha encountered")

            print("Starting granular content extraction...")
            full_ai_text, source_links = await self._extract_granular_content(page)
            print(f"✓ Extracted {len(source_links)} total sources from content.")
            
            result = ScrapingResult(
                query=query,
                ai_overview_text=full_ai_text,
                source_links=source_links,
                total_interactions=len(source_links),
                success=bool(full_ai_text.strip()),
                timestamp=timestamp
            )

            if save_files:
                await self._save_results(result)
                await self._save_verbose_log(result)
            return result

        except Exception as e:
            print(f"Scraping error: {e}")
            self.log_messages.append(f"\nCRITICAL ERROR: {e}")
            error_result = ScrapingResult(
                query=query, ai_overview_text="", source_links=[], total_interactions=0,
                success=False, timestamp=timestamp, error_message=str(e)
            )
            if save_files:
                await self._save_verbose_log(error_result)
            return error_result

    async def _wait_for_full_response(self, page: Page, timeout_ms: int):
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_path = f"debug_failure_{timestamp_str}.png"
        
        try:
            related_section_header = page.locator('div.font-display:has-text("Related")')
            await related_section_header.first.wait_for(state="visible", timeout=timeout_ms)
            print("✓ Full response generated (detected 'Related' section).")
        except Exception as e:
            try:
                await page.screenshot(path=screenshot_path, full_page=True)
                print(f"⚠ Screenshot saved to {screenshot_path} upon response timeout.")
            except Exception as se:
                print(f"⚠ Error taking screenshot: {se}")
                
            print(f"⚠ Timed out waiting for the full response: {e}. Proceeding with partial content.")

    async def _handle_popups(self, page: Page):
        try:
            close_button_selectors = [
                'button[aria-label="Close"]',
                'div[role="dialog"] button:has-text("No thanks")',
                '.modal-content button.close'
            ]
            for selector in close_button_selectors:
                close_button = page.locator(selector).first
                if await close_button.is_visible(timeout=1500):
                    await close_button.click()
                    await self._random_wait(0.5, 1.0)
                    print(f"✓ Closed initial popup using selector: {selector}")
                    return
        except: 
            pass
        self.log_messages.append("No initial popup detected or closed.")

    async def _human_search(self, page: Page, query: str):
        try:
            self.log_messages.append("Attempting primary search method.")
            await page.wait_for_load_state('domcontentloaded')
            await self._random_wait(1.0, 2.0)

            search_box = page.locator("#ask-input")

            if await search_box.count() == 0 or not await search_box.is_visible(timeout=5000):
                for frame in page.frames:
                    box_in_frame = frame.locator("textarea[placeholder*='Ask anything']")
                    if await box_in_frame.count() > 0:
                        search_box = box_in_frame
                        print("✓ Found visible search box in iframe/textarea.")
                        break

            if not search_box or await search_box.count() == 0:
                raise Exception("Could not find a valid search box.")

            await search_box.focus()
            await self._random_wait(0.5, 1.0)
            await search_box.fill(query, timeout=5000)
            await self._random_wait(1.5, 3.0)

            await page.keyboard.press("Enter")
            self.log_messages.append("Submitted search via Enter key.")

            try:
                await page.wait_for_url("**/search**", timeout=30000)
            except Exception:
                try:
                    current_url = page.url
                except Exception:
                    current_url = ""
                if not (current_url and "/search" in current_url):
                    raise
                else:
                    print("✓ Detected navigation to a search URL despite URL wait timing out.")

            try:
                await page.wait_for_selector('div[id^="markdown-content-"]', timeout=30000)
            except Exception:
                self.log_messages.append("Result container did not appear within timeout; continuing anyway.")

            print("✓ Successfully navigated to search results (via UI).")

        except Exception as e:
            self.log_messages.append(f"Primary search failed to navigate: {e}. Considering direct URL fallback.")
            print(f"Primary search failed to trigger navigation, evaluating direct fallback: {e}")

            try:
                current_url = page.url
            except Exception:
                current_url = ""

            if current_url and "/search" in current_url:
                print("✓ Current page URL indicates search results are present — skipping direct fallback.")
                self.log_messages.append("Skipped direct fallback because page.url indicated search results.")
                return

            await page.goto(f"https://www.perplexity.ai/search?q={urllib.parse.quote_plus(query)}", wait_until="domcontentloaded")
            print("✓ Executed direct URL fallback.")
            self.log_messages.append("Executed direct URL fallback.")

    async def _extract_granular_content(self, page: Page) -> tuple[str, List[SourceLink]]:
        """
        Enhanced extraction that properly handles Perplexity's citation structure:
        1. Top source cards (grid layout) - reference links at the top
        2. Inline citations within response text - with proper context extraction
        3. Table citations - handling citations within table cells
        """
        all_source_links = []
        full_text_parts = []
        processed_urls = set()
        extraction_order = 0
        
        # --- STEP 1: Extract Top Source Cards (Grid Layout) ---
        print("\n" + "="*60)
        print("STEP 1: Extracting Top Source Cards (Grid Layout)")
        print("="*60)
        try:
            # Look for the grid container that holds source cards
            source_grid = page.locator('div.gap-sm.grid.grid-cols-3, div[class*="grid"][class*="grid-cols"]').first
            
            # Each source card is within a div.min-w-0 containing an anchor
            source_cards = source_grid.locator('div.min-w-0 > div > a[href][target="_blank"]')
            
            card_count = await source_cards.count()
            print(f"Found {card_count} source cards in grid layout")
            
            for i in range(card_count):
                card = source_cards.nth(i)
                try:
                    # Extract URL
                    url = await card.get_attribute("href")
                    if not url:
                        continue
                    
                    cleaned_url = self._clean_url(url)
                    if not cleaned_url or cleaned_url in processed_urls:
                        continue
                    
                    # Extract domain name - look for the div with class line-clamp-1 containing domain
                    domain_elem = card.locator('div.line-clamp-1.min-w-0.grow.break-all')
                    domain = ""
                    if await domain_elem.count() > 0:
                        domain = (await domain_elem.first.inner_text()).strip()
                    
                    # Extract title - look for span with class line-clamp-1 or line-clamp-2
                    title_elem = card.locator('span.line-clamp-1, span[class*="line-clamp"]')
                    title = ""
                    if await title_elem.count() > 0:
                        title = (await title_elem.last.inner_text()).strip()
                    
                    # Use title if available, otherwise domain
                    display_text = title if title else domain
                    
                    if self._is_valid_source_link(cleaned_url, display_text):
                        extraction_order += 1
                        source_link = SourceLink(
                            text=display_text,
                            url=cleaned_url,
                            raw_url=url,
                            related_claim="Top source card - General reference",
                            extraction_order=extraction_order
                        )
                        all_source_links.append(source_link)
                        processed_urls.add(cleaned_url)
                        print(f"  ✓ Card {extraction_order}: [{display_text[:40]}] → {cleaned_url[:50]}...")
                        
                except Exception as e:
                    print(f"  ✗ Error extracting card {i+1}: {e}")
                    continue
                    
        except Exception as e:
            print(f"Warning: Could not extract source cards from grid: {e}")
        
        print(f"\n✓ Extracted {extraction_order} source cards from grid layout\n")
        
        # --- STEP 2: Extract Response Content with Inline Citations ---
        print("="*60)
        print("STEP 2: Extracting Response Content with Inline Citations")
        print("="*60)
        
        try:
            response_container = page.locator('div[id^="markdown-content-"]').first
            
            # Get the entire HTML structure to work with
            container_html = await response_container.inner_html()
            
            # Extract all text content for AI overview (keeping this as is)
            all_elements = await response_container.locator("p, ul, ol, h2, h3, h4, li, td").all()
            processed_blocks_text = set()
            
            for elem in all_elements:
                try:
                    if not await elem.is_visible():
                        continue
                    
                    # Get clean text without citation badges for AI overview
                    elem_handle = await elem.element_handle()
                    if elem_handle:
                        cleaned_text = await elem_handle.evaluate('''
                            el => {
                                const clone = el.cloneNode(true);
                                // Remove all citation elements
                                clone.querySelectorAll('span.citation, span.citation-nbsp').forEach(cite => cite.remove());
                                return clone.innerText;
                            }
                        ''')
                        
                        cleaned_text = self._clean_text_chunk(cleaned_text)
                        if cleaned_text and cleaned_text not in processed_blocks_text and len(cleaned_text) > 10:
                            full_text_parts.append(cleaned_text)
                            processed_blocks_text.add(cleaned_text)
                except Exception as e:
                    continue
            
            # Now extract inline citations with their context
            print("\nExtracting inline citations with context...")
            
            # Find all citation elements
            citation_spans = response_container.locator('span.citation.inline')
            citation_count = await citation_spans.count()
            print(f"Found {citation_count} inline citation elements")
            
            for cite_idx in range(citation_count):
                citation_span = citation_spans.nth(cite_idx)
                try:
                    # Get the citation link
                    citation_link = citation_span.locator('a[href]').first
                    if await citation_link.count() == 0:
                        continue
                    
                    url = await citation_link.get_attribute("href")
                    if not url:
                        continue
                    
                    cleaned_url = self._clean_url(url)
                    if not cleaned_url or cleaned_url in processed_urls:
                        continue
                    
                    # Extract domain name from the nested span structure
                    # Pattern: span.citation > a > span > span.overflow-hidden
                    domain_span = citation_link.locator('span[class*="overflow-hidden"]').first
                    domain_name = ""
                    if await domain_span.count() > 0:
                        domain_name = (await domain_span.inner_text()).strip()
                    
                    # Check for multiple sources indicator (+N)
                    plus_indicator_span = citation_link.locator('span.opacity-50')
                    plus_count = ""
                    if await plus_indicator_span.count() > 0:
                        plus_count = (await plus_indicator_span.inner_text()).strip()
                    
                    display_text = f"{domain_name}{plus_count}".strip()
                    
                    # Extract the context (the text being cited)
                    # Find the parent element that contains the citation
                    parent_elem = citation_span.locator('xpath=ancestor::p | ancestor::td | ancestor::li').first
                    
                    context_text = "Inline citation"
                    if await parent_elem.count() > 0:
                        # Get the HTML of parent element
                        parent_html = await parent_elem.inner_html()
                        
                        # Find where the citation appears in the parent HTML
                        # Get text before the citation marker (citation-nbsp)
                        parent_text_handle = await parent_elem.element_handle()
                        if parent_text_handle:
                            # Get text content before citation
                            context_text = await parent_text_handle.evaluate('''
                                (el, citationSpan) => {
                                    const clone = el.cloneNode(true);
                                    
                                    // Find the citation span in the clone
                                    const citations = clone.querySelectorAll('span.citation');
                                    let targetCitation = null;
                                    
                                    // Get the outer HTML to match
                                    const citationHTML = citationSpan.outerHTML;
                                    
                                    for (let cite of citations) {
                                        if (cite.outerHTML === citationHTML) {
                                            targetCitation = cite;
                                            break;
                                        }
                                    }
                                    
                                    if (targetCitation) {
                                        // Get all text before this citation
                                        let textBefore = '';
                                        let node = clone.firstChild;
                                        
                                        while (node) {
                                            if (node === targetCitation) {
                                                break;
                                            }
                                            if (node.nodeType === Node.TEXT_NODE) {
                                                textBefore += node.textContent;
                                            } else if (node.nodeType === Node.ELEMENT_NODE && !node.classList.contains('citation')) {
                                                textBefore += node.innerText || node.textContent;
                                            }
                                            node = node.nextSibling;
                                        }
                                        
                                        // Get the last sentence or clause before citation
                                        textBefore = textBefore.trim();
                                        
                                        // Try to get last sentence
                                        const sentences = textBefore.split(/[.!?]+/);
                                        if (sentences.length > 0) {
                                            const lastSentence = sentences[sentences.length - 1].trim();
                                            if (lastSentence.length > 20) {
                                                return lastSentence;
                                            }
                                        }
                                        
                                        // Return last 200 chars if no good sentence found
                                        return textBefore.slice(-200);
                                    }
                                    
                                    // Fallback: return all text without citations
                                    clone.querySelectorAll('span.citation').forEach(c => c.remove());
                                    return clone.innerText.trim();
                                }
                            ''', await citation_span.element_handle())
                            
                            context_text = self._clean_text_chunk(context_text)
                            if not context_text or len(context_text) < 10:
                                # Fallback: get parent text
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
                        
                        # Normalize display text
                        normalized_text = self._normalize_citation_text(display_text or domain_name or "Citation")
                        
                        source_link = SourceLink(
                            text=normalized_text,
                            url=cleaned_url,
                            raw_url=url,
                            related_claim=context_text,
                            extraction_order=extraction_order
                        )
                        all_source_links.append(source_link)
                        processed_urls.add(cleaned_url)
                        
                        # Show context snippet
                        context_preview = context_text[:80].replace('\n', ' ')
                        print(f"  ✓ Citation {extraction_order}: [{normalized_text}]")
                        print(f"     Context: \"{context_preview}...\"")
                        print(f"     URL: {cleaned_url[:60]}...")
                        
                except Exception as e:
                    print(f"  ✗ Error extracting citation {cite_idx + 1}: {e}")
                    continue
            
        except Exception as e:
            print(f"Error extracting response content: {e}")
        
        # --- STEP 3: Handle Table Citations ---
        print("\n" + "="*60)
        print("STEP 3: Checking for Table Citations")
        print("="*60)
        
        try:
            # Look for tables in the response
            tables = response_container.locator('table')
            table_count = await tables.count()
            
            if table_count > 0:
                print(f"Found {table_count} table(s), scanning for citations...")
                
                for table_idx in range(table_count):
                    table = tables.nth(table_idx)
                    
                    # Get all cells that might contain citations
                    cells_with_citations = table.locator('td:has(span.citation)')
                    cell_count = await cells_with_citations.count()
                    
                    print(f"  Table {table_idx + 1}: Found {cell_count} cells with citations")
                    
                    for cell_idx in range(cell_count):
                        cell = cells_with_citations.nth(cell_idx)
                        try:
                            # Get cell text without citations for context
                            cell_text = await cell.evaluate('''
                                el => {
                                    const clone = el.cloneNode(true);
                                    clone.querySelectorAll('span.citation').forEach(c => c.remove());
                                    return clone.innerText;
                                }
                            ''')
                            cell_text = self._clean_text_chunk(cell_text)
                            
                            # Get all citations in this cell
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
                                    
                                    # Extract domain
                                    domain_span = cite_link.locator('span[class*="overflow-hidden"]').first
                                    domain_name = ""
                                    if await domain_span.count() > 0:
                                        domain_name = (await domain_span.inner_text()).strip()
                                    
                                    # Check for +N indicator
                                    plus_span = cite_link.locator('span.opacity-50')
                                    plus_text = ""
                                    if await plus_span.count() > 0:
                                        plus_text = (await plus_span.inner_text()).strip()
                                    
                                    display_text = f"{domain_name}{plus_text}".strip()
                                    
                                    if self._is_valid_source_link(cleaned_url, display_text):
                                        extraction_order += 1
                                        
                                        normalized_text = self._normalize_citation_text(display_text or domain_name)
                                        
                                        source_link = SourceLink(
                                            text=normalized_text,
                                            url=cleaned_url,
                                            raw_url=url,
                                            related_claim=f"Table citation: {cell_text[:150]}",
                                            extraction_order=extraction_order
                                        )
                                        all_source_links.append(source_link)
                                        processed_urls.add(cleaned_url)
                                        
                                        print(f"    ✓ Table Citation {extraction_order}: [{normalized_text}]")
                                        print(f"       Cell Context: \"{cell_text[:60]}...\"")
                                        
                                except Exception as e:
                                    print(f"      ✗ Error extracting table citation: {e}")
                                    continue
                            
                        except Exception as e:
                            print(f"    ✗ Error processing table cell: {e}")
                            continue
                            
            else:
                print("No tables found in response")
                
        except Exception as e:
            print(f"Error scanning tables: {e}")
        
        # Compile final results
        full_ai_text = "\n\n".join(full_text_parts)
        
        print("\n" + "="*60)
        print("EXTRACTION SUMMARY")
        print("="*60)
        print(f"  ✓ Total sources extracted: {len(all_source_links)}")
        print(f"  ✓ Unique URLs: {len(processed_urls)}")
        print(f"  ✓ Response text length: {len(full_ai_text)} characters")
        print(f"  ✓ Response paragraphs: {len(full_text_parts)}")
        print("="*60 + "\n")
        
        return full_ai_text, all_source_links

    def _normalize_citation_text(self, text: str) -> str:
        """
        Normalize citation badge text for better readability.
        Handles cases like 'visuresolutions+8' → 'visuresolutions (+8 sources)'
        """
        if not text:
            return ""
        
        # Handle pattern like "domain+N" or "domain +N"
        match = re.match(r'(.+?)\s*\+(\d+)$', text)
        if match:
            base, count = match.groups()
            return f"{base.strip()} (+{count} sources)"
        
        return text.strip()

    def _clean_url(self, url: str) -> str:
        if not url: 
            return ""
        url_parts = urllib.parse.urlparse(url)
        cleaned_url = urllib.parse.urlunparse(url_parts[:3] + ('', '', ''))
        return f"https://www.perplexity.ai{cleaned_url}" if cleaned_url.startswith("/") else cleaned_url

    def _is_valid_source_link(self, url: str, text: str) -> bool:
        if not url or not text.strip(): 
            return False
        url_lower = url.lower()
        if any(scheme in url_lower for scheme in ["javascript:", "mailto:", "tel:"]): 
            return False
        return url_lower.startswith("http")

    def _clean_text_chunk(self, text: str) -> str:
        """
        Enhanced cleaning for Perplexity response text.
        Removes citation artifacts, pricing info, and promotional content.
        """
        if not text:
            return ""
        
        # Remove citation artifacts
        text = re.sub(r'\[\d+\]', '', text)  # Remove [1], [2] style citations
        text = re.sub(r'\$\d+\.\d+', "", text)  # Remove prices
        text = re.sub(r"buy now", "", text, flags=re.IGNORECASE)  # Remove promotional text
        
        # Remove zero-width spaces and other invisible characters
        text = re.sub(r'[\u200B-\u200D\uFEFF]', '', text)
        
        # Remove trailing domain patterns
        text = re.sub(r'\s+([a-zA-Z0-9-]+\.[a-zA-Z]{2,})(\s*\+\d+)?\s*$', '', text)
        
        lines = text.splitlines()
        cleaned_lines = []
        
        for line in lines:
            stripped_line = line.strip()
            if not stripped_line:
                continue
            
            # Skip lines that are just domain names or very short
            if len(stripped_line) > 10 and not re.match(r'^[a-zA-Z0-9-]+\.[a-zA-Z]{2,}$', stripped_line):
                cleaned_lines.append(stripped_line)
        
        return "\n".join(cleaned_lines).strip()

    def _is_bot_detected(self, page_text: str) -> bool:
        return any(phrase in page_text.lower() for phrase in ["verify you are human", "captcha", "are you a robot"])

    async def _random_wait(self, min_seconds: float, max_seconds: float):
        await asyncio.sleep(random.uniform(min_seconds, max_seconds))

    async def _save_results(self, result: ScrapingResult):
        timestamp_str = datetime.fromisoformat(result.timestamp).strftime("%Y%m%d_%H%M%S")
        try:
            txt_filename = f"perplexity_ai_answer_{timestamp_str}.txt"
            with open(txt_filename, "w", encoding="utf-8") as f:
                f.write(f"Query: {result.query}\nSuccess: {result.success}\n\n")
                f.write("AI OVERVIEW TEXT:\n-----------------\n" + result.ai_overview_text + "\n\n")
                f.write(f"SOURCE LINKS ({len(result.source_links)} total):\n-----------------\n")
                for link in result.source_links:
                    claim_snippet = link.related_claim[:150].replace('\n', ' ')
                    f.write(f"\n[{link.extraction_order}] {link.text}\n")
                    f.write(f"    URL: {link.url}\n")
                    f.write(f"    Context: {claim_snippet}...\n")
            print(f"✓ Results saved to {txt_filename}")
        except Exception as e: 
            print(f"Error saving TXT file: {e}")
        try:
            json_filename = f"perplexity_ai_answer_{timestamp_str}.json"
            with open(json_filename, "w", encoding="utf-8") as f:
                json.dump(asdict(result), f, indent=2, ensure_ascii=False)
            print(f"✓ Results saved to {json_filename}")
        except Exception as e: 
            print(f"Error saving JSON file: {e}")

    async def _save_verbose_log(self, result: ScrapingResult):
        timestamp_str = datetime.fromisoformat(result.timestamp).strftime("%Y%m%d_%H%M%S")
        log_filename = f"perplexity_ai_answer_LOG_{timestamp_str}.txt"
        with open(log_filename, "w", encoding="utf-8") as f:
            f.write("\n".join(self.log_messages))
        print(f"✓ Verbose log saved to {log_filename}")


# ==================== BROWSER MANAGER ====================

class BrowserManager:
    def __init__(self):
        self.browser: Optional[Browser] = None
        self.playwright = None
        self.stealth = None

    async def start(self):
        """Initialize browser with stealth mode"""
        if self.browser is None:
            self.stealth = Stealth()
            self.playwright = await self.stealth.use_async(async_playwright()).__aenter__()
            # --- THIS IS THE CHANGED PART ---
            proxy_server = os.environ.get("PROXY_SERVER")
            proxy_username = os.environ.get("PROXY_USERNAME")
            proxy_password = os.environ.get("PROXY_PASSWORD")
            self.browser = await self.playwright.chromium.launch(
                headless=True,
                # proxy={
                #     "server": 'in-pr.oxylabs.io:20000',
                #     "username": "godseye_hY287",
                #     "password": "Godseye+584101",
                # },
                proxy={
                    "server": proxy_server,
                    "username": proxy_username,
                    "password": proxy_password,
                },
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-accelerated-2d-canvas',
                    '--disable-gpu',
                    '--disable-blink-features=AutomationControlled'
                ]
            )
            print("✓ Browser initialized successfully")

    async def stop(self):
        """Close browser and cleanup"""
        try:
            if self.browser and not self.browser.is_connected():
                print("✓ Browser already disconnected, skipping close")
                self.browser = None
            elif self.browser:
                await self.browser.close()
                self.browser = None
                print("✓ Browser closed")
        except Exception as e:
            print(f"⚠ Error closing browser (may already be closed): {e}")
            self.browser = None
        
        try:
            if self.playwright:
                await self.playwright.__aexit__(None, None, None)
                self.playwright = None
        except Exception as e:
            print(f"⚠ Error closing playwright (may already be closed): {e}")
            self.playwright = None

    async def create_page(self, location: str, user_agent: str):
        """Create a new page with location settings"""
        if location not in LOCATION_CONFIG:
            raise ValueError(f"Invalid location: {location}. Must be 'India' or 'USA'")

        location_settings = LOCATION_CONFIG[location]

        context = await self.browser.new_context(
            user_agent=user_agent,
            viewport={'width': 1920, 'height': 1080},
            **location_settings
        )
        await context.grant_permissions(location_settings.get('permissions', []))

        page = await context.new_page()
        return page, context


# ==================== FASTAPI APP ====================

browser_manager = BrowserManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage browser lifecycle"""
    await browser_manager.start()
    yield
    await browser_manager.stop()


app = FastAPI(
    title="Perplexity AI Scraper API",
    description="API for scraping search results from Perplexity AI",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware configuration
origins = [
    "http://localhost",
    "http://localhost:8080",
    "http://localhost:3000",

    # Your production domains
    "https://godseyes.world",
    "https://www.godseyes.world",
    
    # You can add these if you test without HTTPS,
    # but remove them in final production.
    "http://godseyes.world",
    "http://www.godseyes.world",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "online",
        "service": "Perplexity AI Scraper API",
        "version": "1.0.0"
    }


@app.post("/scrape", response_model=ScrapeResponse)
async def scrape_perplexity(request: ScrapeRequest):
    """
    Scrape Perplexity AI for a given query
    
    - **query**: Search query to scrape
    - **location**: Location setting (India or USA)
    - **save_files**: Whether to save results to local files
    """
    scraper = PerplexityScraper()
    page = None
    context = None

    try:
        # Validate location
        if request.location not in LOCATION_CONFIG:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid location: {request.location}. Must be 'India' or 'USA'"
            )

        # Create page with settings
        user_agent = random.choice(scraper.user_agents)
        page, context = await browser_manager.create_page(request.location, user_agent)

        print(f"Starting scrape for query: {request.query} (Location: {request.location})")

        # Perform scraping
        result = await scraper.scrape(page, request.query, request.save_files)

        # Convert to response model
        source_links_response = [
            SourceLinkResponse(
                text=link.text,
                url=link.url,
                raw_url=link.raw_url,
                highlight_fragment=link.highlight_fragment,
                related_claim=link.related_claim,
                extraction_order=link.extraction_order
            )
            for link in result.source_links
        ]

        response = ScrapeResponse(
            query=result.query,
            ai_overview_text=result.ai_overview_text,
            source_links=source_links_response,
            total_interactions=result.total_interactions,
            success=result.success,
            timestamp=result.timestamp,
            error_message=result.error_message
        )

        return response

    except Exception as e:
        print(f"Error in scrape endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        # Cleanup
        if context:
            await context.close()
        if page and not page.is_closed():
            await page.close()


@app.get("/health")
async def health_check():
    """Check if browser is ready"""
    return {
        "status": "healthy" if browser_manager.browser else "unhealthy",
        "browser_ready": browser_manager.browser is not None
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
