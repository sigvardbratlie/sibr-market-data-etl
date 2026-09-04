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
    use_playwright_listings = False
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
        output = response.xpath(f"normalize-space(//ul[contains(@class, 'space-y-6')]//span[contains(@class, "
                              f"'font-bold') and normalize-space(.)='{label}:']/following-sibling::a[1]/text())").get()
        if not output or output == ',':
            output = None
        return output

    def get_info(self, response, label):
        """Extract info with multiple fallback selectors"""
        output = response.xpath(f"normalize-space(//ul[contains(@class, 'space-y-6')]//span[contains(@class, "
                       f"'font-bold') and normalize-space(.)='{label}:']/following-sibling::text()[normalize-space()][1])").get()
        if not output or output == ',':
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
        if not output or output == ',':
            output = None
        return output


    async def parse(self, response):
        if 'playwright_page' in response.meta:
            page = response.meta["playwright_page"]
            await page.close()
        item = JobItem()

        # Basic info
        item['item_id'] = response.css('li strong:contains("FINN-kode") + span::text').get() or response.css('dt:contains("FINN-kode") + dd::text').get()
        item['title'] = response.css('h2.t2.md\\:t1::text').get() or response.css('h1.t3::text').get()
        item['description'] = response.xpath('normalize-space((//div[contains(@class,"import-decoration")])[1])').get() or None
        item['url'] = response.url
        item['address'] = response.xpath('normalize-space(//h2[contains(@class,"t3") and contains(text(),"Firmaets beliggenhet")]/following-sibling::p[1])').get() or None
        item['last_updated'] = response.css('strong:contains("Sist endret") + time::text').get() or response.css('dt:contains("Sist endret") + dd::text').get()
        item['scrape_date'] = datetime.now().strftime('%Y-%m-%d')
        item['country'] = 'NO'
        item['dealer'] = None
        item['contact_person'] = response.css('p.contact-card-name::text').get() or self.get_all_info(response,'Kontaktperson') or self.get_info_dt(response,'Kontaktperson')
        item['phone'] = self.get_contact_info(response, 'Mobil') or self.get_contact_info(response, 'Telefon')
        item['email'] = self.get_contact_info(response, 'E-post')
        item['web'] = response.css('w-link:contains("Hjemmeside")::attr(href)').get() or response.css('ul.mb-0 li a:contains("Hjemmeside")::attr(href)').get()

        item['contact_title'] = response.css('p.contact-card-name + p::text').get() or self.get_all_info(response,'Stillingstittel') or self.get_info_dt(response,'Stillingstittel')
        info_line_parts = response.css('div.text-caption.md\\:text-body.font-bold.md\\:font-normal::text').getall()
        info_line = ''.join(info_line_parts).strip() if info_line_parts else None
        item['subtitle'] = info_line
        item['employer'] = response.css('div.header-logo-container strong::text').get() or response.css('dt:contains("Arbeidsgiver") + dd::text').get()
        item['about_employer'] = response.xpath('normalize-space(//h2[contains(text(),"Om arbeidsgiveren")]/following-sibling::div[contains(@class,"import-decoration")][1])').get() or None
        item['sector'] = response.css('li.flex span:contains("Sektor") + strong::text').get()
        item['industry'] = self.get_all_info(response,'Bransje') or response.css('dt:contains("Bransje") + dd::text').getall()
        item['job_function'] = (self.get_all_info(response,'Stillingsfunksjon')
                                or self.get_info(response,'Stillingsfunksjon') or response.css('dt:contains("Stillingsfunksjon") + dd::text').getall())
        item['deadline'] = response.css('li.flex span:contains("Søknadsfrist") + strong::text').get()
        item['employment_type'] = info_line.split('∙')[0].strip() if info_line else (self.get_info(response, 'Ansettelsesform') or response.css('dt:contains("Ansettelsesform") + dd::text').get())

        item['positions_available'] = response.css('li.flex span:contains("Antall stillinger") + strong::text').get()
        item['work_language'] = response.css('li.flex span:contains("Arbeidsspråk") + strong::text').get()
        item['remote_work'] = response.css('li.flex span:contains("Mulighet for hjemmekontor") + strong::text').get()
        item['location'] = response.xpath( '//li[span[contains(normalize-space(), "Sted")]]').xpath('string(.)').get()
        item['keywords'] = response.css('h2.t3:contains("Nøkkelord") + p::text').get()

        yield item
