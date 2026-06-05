import scrapy
from scrapy_playwright.page import PageMethod
import asyncio
import json
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

class FinnBaseSpider(scrapy.Spider):
    allowed_domains = ["www.finn.no"]
    use_playwright_listings = False
    use_playwright_items = False
    use_proxy = False
    count = 0
    listing_article_selector = (
        'article.sf-search-ad, '
        'article[data-testid="search-result-ad"], '
        'article[data-testid="search-result-item"]'
    )

    custom_settings = {
        'DOWNLOAD_HANDLERS': {
            "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
            "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",

        },
        'TWISTED_REACTOR': 'twisted.internet.asyncioreactor.AsyncioSelectorReactor',
        'PLAYWRIGHT_BROWSER_TYPE': 'chromium',
        'PLAYWRIGHT_LAUNCH_OPTIONS': {
            'headless': True,
            # 'args': [
            #     '--disable-gpu',
            #     '--disable-dev-shm-usage',
            #     '--disable-setuid-sandbox',
            #     '--no-sandbox',
            #     '--disable-extensions',
            #     '--disable-logging',
            # ]
        },
        'PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT': 30000,
        'PLAYWRIGHT_BROWSER_CONTEXT_ARGS': {
            "java_script_enabled": True,
            "ignore_https_errors": True,
            "viewport": {
                "width": 1280,
                "height": 720
            },
            "bypass_csp": True
        },

        # 'DOWNLOAD_DELAY': 0.3,
        'REACTOR_THREADPOOL_MAXSIZE': 20,
        'PLAYWRIGHT_ABORT_REQUEST': lambda req: not any(
            x in req.resource_type for x in ['document', 'script', 'xhr', 'fetch']),
    }

    def __init__(self, use_playwright_listings=None, use_playwright_items = None,*args, **kwargs):
        super().__init__(*args, **kwargs)
        if use_playwright_listings is not None:
            self.use_playwright_listings = str(use_playwright_listings).lower() == 'true'
        if use_playwright_items is not None:
            self.use_playwright_items = str(use_playwright_items).lower() == 'true'

    def _get_company_data(self, response):
        """Get company data from script tag"""
        script_tag = response.xpath('//script[@data-company-profile-data]').get()
        if script_tag:
            # Fjern <script> tags og parse JSON innholdet
            script_content = response.xpath('//script[@data-company-profile-data]/text()').get()
            if script_content:
                data = json.loads(script_content)
                if 'companyProfile' in data:
                    return data['companyProfile']
        return None

    def get_dealer(self, response):
        """Get dealer information"""
        cp = self._get_company_data(response)
        if cp:
            return cp.get('orgName')

    def get_contact_person(self, response):
        profile = self._get_company_data(response)
        if profile:
            if 'contacts' in profile and profile['contacts']:
                return profile['contacts'][0].get('name')
            elif 'contact' in profile:
                return profile['contact'].get('name')

    def get_phone(self, response):
        profile = self._get_company_data(response)
        if profile:
            if 'contacts' in profile and profile['contacts']:
                phones = profile['contacts'][0].get('phone', [])
                if phones and 'phoneFormatted' in phones[0]:
                    return phones[0]['phoneFormatted']
                elif phones and 'tel' in phones[0]:
                    return phones[0]['tel']
            elif 'contact' in profile:
                phones = profile['contact'].get('phone', [])
                if phones and 'phoneFormatted' in phones[0]:
                    return phones[0]['phoneFormatted']

    def get_email(self, response):
        profile = self._get_company_data(response)
        if profile:
            if 'contacts' in profile and profile['contacts']:
                return profile['contacts'][0].get('email')
            elif 'contact' in profile:
                return profile['contact'].get('email')

    async def errback(self,failure):
        if 'playwright_page' in failure.request.meta:
            page = failure.request.meta["playwright_page"]
            await asyncio.sleep(2)
            await page.close()
        self.logger.error(repr(failure))

    async def start(self):
        if not self.start_urls:
            self.logger.warning("No start URLs configured for spider %s", self.name)
        for url in self.start_urls:
            if not url or not url.startswith(("http://", "https://")):
                self.logger.warning("Skipping malformed start URL: %s", url)
                continue
            if url.count("http://") + url.count("https://") > 1:
                self.logger.warning("Skipping malformed start URL (multiple schemes): %s", url)
                continue
            meta = {'errback': self.errback}

            if "ad.html" in url or "/mobility/item/" in url:
                if self.use_playwright_items:
                    meta['playwright'] = True
                    meta['playwright_include_page'] = True
                yield scrapy.Request(url=url, meta=meta, callback=self.parse)

            else:
                if self.use_playwright_listings:
                    meta['playwright'] = True
                    meta['playwright_include_page'] = True
                    meta['playwright_page_methods'] = [
                        PageMethod('wait_for_selector', self.listing_article_selector),
                        PageMethod('wait_for_load_state', 'networkidle')]
                if self.use_proxy:
                    meta['proxy'] = 'http://sigvarbrat49411:jgytj0vcj8@154.21.32.105:21309'

                yield scrapy.Request(url=url,
                                     meta=meta,callback=self.parse_listings_page)

    async def parse_listings_page(self, response):
        if 'playwright_page' in response.meta:
            page = response.meta["playwright_page"]
            await page.close()
        self.count += 1
        if self.count % 500 == 0:
            self.logger.info(f'Processed {self.count} listings so far. Processing {response.url}')
        article_urls = self.get_listing_urls(response)
        if not article_urls:
            title = response.css('title::text').get()
            selector_counts = {
                "articles": len(response.css(self.listing_article_selector)),
                "ad_links": len(response.css('a[href*="ad.html"], a[href*="/mobility/item/"]')),
            }
            self.logger.warning(
                "No listing URLs found on %s (status=%s, title=%r). Selector counts: %s",
                response.url,
                response.status,
                title,
                selector_counts,
            )
        else:
            self.logger.debug("Found %d listing URLs on %s", len(article_urls), response.url)
        for url in article_urls:
            meta = {'errback': self.errback}
            if self.use_playwright_items:
                meta['playwright'] = True
                meta['playwright_include_page'] = True
            yield scrapy.Request(url=url, meta=meta, callback=self.parse)

        if article_urls:
            next_page = self.get_next_page_request(response)
            if next_page:
                yield next_page

    def get_listing_urls(self, response):
        """Extract item URLs from a listing page. Override in subclasses with different HTML."""
        urls = []
        articles = response.css(self.listing_article_selector)
        if articles:
            for article in articles:
                href = article.css(
                    'a[data-testid="search-result-title"]::attr(href), '
                    'h2 a::attr(href), '
                    'a::attr(href)'
                ).get()
                if href:
                    urls.append(response.urljoin(href))
            if urls:
                return list(dict.fromkeys(urls))

        hrefs = response.css('a[href*="ad.html"], a[href*="/mobility/item/"]::attr(href)').getall()
        if hrefs:
            return list(dict.fromkeys(response.urljoin(href) for href in hrefs if href))

        return []

    async def parse(self, response):
        raise NotImplementedError("You must implement the parse method in your spider")


    def get_next_page_request(self, response):
        next_page_url = None

        # Strategy 1: <w-pagination> web component (mc, car, boat, home, ...)
        # Pagination content is in shadow DOM, but attributes are in the regular DOM
        pagination = response.css('w-pagination')
        if pagination:
            current_page = int(pagination.attrib.get('current-page', 1))
            total_pages = int(pagination.attrib.get('pages', 1))
            base_url = pagination.attrib.get('base-url', '')
            if current_page < total_pages and base_url:
                next_page_url = response.urljoin(base_url + str(current_page + 1))

        # Strategy 2: plain <a rel="next"> (jobs, older pages)
        if not next_page_url:
            next_href = response.css('a[rel="next"]::attr(href)').get()
            if next_href:
                next_page_url = response.urljoin(next_href)

        if not next_page_url:
            return None

        meta = {'errback': self.errback}
        if self.use_playwright_listings:
            meta['playwright'] = True
            meta['playwright_include_page'] = True
            meta['playwright_page_methods'] = [
                PageMethod('wait_for_selector', self.listing_article_selector),
                PageMethod('wait_for_load_state', 'networkidle')]
        return scrapy.Request(url=next_page_url, meta=meta, callback=self.parse_listings_page)