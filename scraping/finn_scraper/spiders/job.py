from datetime import datetime
from finn_scraper.items import JobItem
from finn_scraper.spiders.finn_base import FinnBaseSpider
import asyncio



class JobSpider(FinnBaseSpider):
    name = 'job'
    _table_name = "jobs"

    start_urls = [
        'https://www.finn.no/job/search',
    ]
    def __init__(self, *args, other_urls=None, **kwargs):
        super().__init__(*args, **kwargs)
        if other_urls:
            self.start_urls = other_urls
        else:
            self.start_urls = self.start_urls
    use_playwright_listing = False
    use_playwright_items = False

    custom_settings = {**FinnBaseSpider.custom_settings,
                       'LOG_LEVEL': 'INFO',
                       }
    def get_listing_urls(self, response):
        return response.css('a.job-card-link::attr(href)').getall()

    @property
    def table_name(self):
        return self._table_name

    def get_contact_info(self, response, label):
        """Extract contact information"""
        output = response.xpath(f"normalize-space(//ul[contains(@class, 'space-y-10')]//span[contains(@class, "
                              f"'font-bold') and normalize-space(.)='{label}:']/following-sibling::a[1]/text())").get()
        if output == ',':
            output = None
        return output

    def get_info(self, response, label):
        """Extract info with multiple fallback selectors"""
        output = response.xpath(f"normalize-space(//ul[contains(@class, 'space-y-10')]//span[contains(@class, "
                       f"'font-bold') and normalize-space(.)='{label}:']/following-sibling::text()[normalize-space()][1])").get()
        if output == ',':
            output = None
        return output

    def get_all_info(self, response, label):
        """
        Henter ut all relatert info for en gitt etikett.
        Denne funksjonen håndterer både ren tekst og tekst som er pakket inn i <a>-tags.
        """
        # Dette XPath-uttrykket finner først <span>-elementet med riktig etikett.
        # Deretter henter det all tekst fra både etterfølgende <a>-tags og rene tekstnoder.
        xpath_query = (
            f"//span[contains(@class, 'font-bold') and normalize-space(.)='{label}:']/following-sibling::a/text() | "
            f"//span[contains(@class, 'font-bold') and normalize-space(.)='{label}:']/following-sibling::text()"
        )

        results = response.xpath(xpath_query).getall()

        # Renser listen for uønskede elementer:
        # 1. Fjerner ledende/etterfølgende mellomrom fra hvert element.
        # 2. Fjerner eventuelle kommaer på slutten av et element.
        # 3. Filtrerer bort elementer som er tomme eller bare inneholder et komma.
        cleaned_results = [
            item.strip().strip(',')
            for item in results
            if item.strip() and item.strip() != ','
        ]

        # Etter rensing kan noen elementer ha blitt tomme (f.eks. hvis de bare var ", ").
        # Vi fjerner disse tomme elementene fra den endelige listen.
        final_list = [item for item in cleaned_results if item]

        return final_list if final_list else None

    def get_info_dt(self,response,label):
        output = response.xpath(
            f"normalize-space(//dl[contains(@class, 'space-y-8')]/dt[contains(@class, 'font-bold') and normalize-space(.)='{label}']/following-sibling::dd[1]/text())").get()
        if output == ',':
            output = None
        return output


    async def parse(self, response):
        if 'playwright_page' in response.meta:
            page = response.meta["playwright_page"]
            await page.close()
        item = JobItem()

        # Basic info
        item['item_id'] = response.css('li.flex.gap-x-16 strong:contains("FINN-kode") + span::text').get() or response.css('dt:contains("FINN-kode") + dd::text').get()
        item['title'] = response.css('h2.t2.md\\:t1::text').get() or response.css('h1.mb-32.md\\:mb-24::text').get()
        item['description'] = response.css('div.import-decoration ::text').getall()
        item['url'] = response.url
        item['address'] = response.css('h2.t3:contains("Firmaets beliggenhet") + p::text').get() or response.css('section[data-testid="job-location"] h2.h3.mb-16::text').get()
        item['last_updated'] = response.css('li.flex.gap-x-16 strong:contains("Sist endret") + time::text').get() or response.css('dt:contains("Sist endret") + dd::text').get()
        item['scrape_date'] = datetime.now().strftime('%Y-%m-%d')
        item['country'] = 'NO'
        item['dealer'] = None
        item['contact_person'] = self.get_all_info(response,'Kontaktperson') or self.get_info_dt(response,'Kontaktperson')
        item['phone'] = self.get_contact_info(response, 'Mobil') or self.get_contact_info(response, 'Telefon')
        item['email'] = self.get_contact_info(response, 'E-post')
        item['web'] = response.css('ul.mb-0 li a:contains("Hjemmeside")::attr(href)').get()

        item['contact_title'] = self.get_all_info(response,'Stillingstittel') or self.get_info_dt(response,'Stillingstittel')
        item['subtitle'] = response.css('h2.t2.md\\:t1 + p::text').get()
        item['employer'] =  response.css('dt:contains("Arbeidsgiver") + dd::text').get() or response.css('h2.t2.md\\:t1 + p::text').get()
        item['about_employer'] = response.css('div.import-decoration::text').getall()
        item['sector'] = response.xpath("//li//span[contains(@class, 'font-bold') and contains(., 'Sektor')]/following::text()[normalize-space()][1]").get()
        item['industry'] = self.get_all_info(response,'Bransje') or response.css('dt:contains("Bransje") + dd::text').getall()
        item['job_function'] = (response.css(f"ul.space-y-10 li span.pr-8.font-bold:contains('Stillingsfunksjon:') ~ a::text").getall()
                                or self.get_info(response,'Stillingsfunksjon') or
                                self.get_all_info(response,'Stillingsfunksjon') or response.css('dt:contains("Stillingsfunksjon") + dd::text').getall())
        item['deadline'] = self.get_info(response, 'Frist') or response.css('dt:contains("Frist") + dd::text').get() or response.css(f"ul.grid li.flex.flex-col:contains('Frist') span.font-bold::text").get()
        item['employment_type'] = self.get_info(response, 'Ansettelsesform') or response.css('dt:contains("Ansettelsesform") + dd::text').get() or response.css(f"ul.grid li.flex.flex-col:contains('Ansettelsesform') span.font-bold::text").get()

        item['positions_available'] = self.get_info(response,'Antall stillinger') or response.css('dt:contains("Antall stillinger") + dd::text').get()
        item['work_language'] = response.xpath("//li//span[contains(@class, 'font-bold') and contains(., 'Arbeidsspråk')]/following::text()[normalize-space()][1]").get()
        item['remote_work'] = response.xpath("//li//span[contains(@class, 'font-bold') and contains(., 'Hjemmekontor')]/following::text()[normalize-space()][1]").get()
        item['location'] = item['location'] = response.xpath("//li[.//span[contains(., 'Sted')]]/text()[normalize-space()]").getall()
        item['keywords'] = response.css('h2.t3:contains("Nøkkelord") + p::text').get()

        yield item
