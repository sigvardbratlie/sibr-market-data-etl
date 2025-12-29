Finn.no Scraper

  Et omfattende web scraping-system bygget med Scrapy for å samle inn annonsedata fra Finn.no. Systemet støtter scraping av flere kategorier og lagrer data direkte til Google BigQuery.

  Oversikt

  Dette prosjektet inneholder spiders for å hente data fra ulike kategorier på Finn.no:
  - Biler (cars)
  - Boliger (homes)
  - Nye boliger (new_homes)
  - Leieobjekter (rentals)
  - Jobber (jobs)
  - Båter (boats)
  - Motorsykler (mcs)

  Alle spiders arver fra en base-spider (FinnBaseSpider) som håndterer felles funksjonalitet som paginering, feilhåndtering og Playwright-integrasjon for JavaScript-tunge sider.

  Arkitektur
```
  scraping/
  ├── finn_scraper/
  │   ├── spiders/          # Spider-implementasjoner
  │   │   ├── finn_base.py  # Base spider med felles funksjonalitet
  │   │   ├── car.py        # Bil-spider
  │   │   ├── home.py       # Bolig-spider
  │   │   ├── new_home.py   # Nybolig-spider
  │   │   ├── job.py        # Jobb-spider
  │   │   ├── boat.py       # Båt-spider
  │   │   ├── mc.py         # MC-spider
  │   │   └── rental.py     # Utleie-spider
  │   ├── items.py          # Item-definisjoner for datastrukturer
  │   ├── pipelines.py      # BigQuery pipeline for datalagring
  │   ├── middlewares.py    # Scrapy middlewares
  │   └── settings.py       # Scrapy-konfigurasjon
  ├── tests/                # Enhetstester for hver spider
  ├── main.py              # Hovedskript for å kjøre spiders
  ├── requirements.txt     # Python-avhengigheter
  └── Dockerfile          # Docker-konfigurasjon
```

  Forutsetninger

  - Python 3.11+
  - Google Cloud-prosjekt med BigQuery aktivert
  - Service account credentials for Google Cloud
  - (Valgfritt) Proxy-tilgang hvis nødvendig

  Installasjon

  1. Klone repository og naviger til scraping-mappen

  cd scraping

  2. Installer avhengigheter

  pip install -r requirements.txt

  3. Installer Playwright browsers

  playwright install chromium

  4. Sett opp miljøvariabler

  Opprett en .env-fil i parent-mappen (sibr-market-backend) med følgende innhold:

  GOOGLE_APPLICATION_CREDENTIALS_FILENAME=sibr-market-xxxxx.json
  GOOGLE_APPLICATION_CREDENTIALS=/path/to/your/service-account-key.json
  GMAIL_PASSWORD=your_app_password  # For email-varsler

  Viktig: Service account må ha tilgang til BigQuery i prosjektet sibr-market og skrivetilgang til dataset raw.

  Konfigurasjon

  BigQuery Setup

  Systemet forventer følgende BigQuery-struktur:
  - Prosjekt: sibr-market
  - Dataset: raw
  - Tabeller: cars, homes, new_homes, rentals, jobs, boats, mcs

  Tabellene opprettes automatisk ved første kjøring hvis de ikke eksisterer (autodetect schema).

  Settings

  Viktige innstillinger i finn_scraper/settings.py:

  CONCURRENT_REQUESTS = 32        # Antall samtidige requests
  BQ_BATCH_SIZE = 5000           # Batcher før skriving til BigQuery
  LOG_LEVEL = 'INFO'             # Logging-nivå
  CLOUD_LOGGING_ENABLED = False  # Google Cloud Logging

  Bruk

  Grunnleggende bruk

  Kjør alle spiders med standard URLs:

  python main.py

  Kjør spesifikke spiders

  # Kjør bare bil-spider
  python main.py --spiders cars

  # Kjør flere spesifikke spiders
  python main.py --spiders cars homes jobs

  Scrape custom URLs

  Fra fil

  Opprett en tekstfil med én URL per linje:

  # urls.txt
  https://www.finn.no/car/used/ad.html?finnkode=123456
  https://www.finn.no/car/used/ad.html?finnkode=789012

  Kjør med:

  python main.py --spiders cars --urls-file urls.txt

  Fra kommandolinjen

  # Scrape spesifikke søkesider
  python main.py --spiders cars --other-urls "https://www.finn.no/mobility/search/car?location=20061"

  # Scrape spesifikke annonser
  python main.py --spiders homes --other-urls "https://www.finn.no/realestate/homes/ad.html?finnkode=123456" "https://www.finn.no/realestate/homes/ad.html?finnkode=789012"

  Logging

  # Endre logging-nivå
  python main.py --log_level DEBUG

  Dataflyt

  1. Spider starter → Henter listesider (search results)
  2. Parser listesider → Finner annonse-URLer
  3. Følger annonse-URLer → Scraper detaljert data
  4. Data sendes til pipeline → BQPipeline prosesserer items
  5. Buffer fylles → Når BQ_BATCH_SIZE nås (5000 items)
  6. Skriv til BigQuery → Batch insert til relevant tabell
  7. NaN rapport → Genereres ved spider completion

  Pipeline-funksjonalitet

  BQPipeline i pipelines.py håndterer:

  - Batching: Buffer items for effektiv BigQuery-skriving
  - NaN-tracking: Sporer manglende data per felt
  - Email-varsler: Sender alert hvis kritiske felter har >80% NaN-rate
  - Auto-schema: Detekterer schema automatisk fra dataframes

  Spider-spesifikke detaljer

  CarSpider (Biler)

  - Standard URLs: 40+ forhåndsdefinerte søk dekker hovedmerker
  - Data: Pris, kilometerstand, årsmodell, utstyr, VIN, service-historikk, etc.
  - Tabell: raw.cars

  HomeSpider (Boliger)

  - Standard URLs: Dekker hele Norge
  - Data: Pris, felleskostnader, fellesgjeld, areal, energimerking, etc.
  - Tabell: raw.homes

  JobSpider (Jobber)

  - Standard URLs: Alle stillingsannonser
  - Data: Arbeidsgiver, bransje, ansettelsestype, søknadsfrist, etc.
  - Tabell: raw.jobs

  Avanserte features

  Playwright-integrasjon

  Noen spiders kan bruke Playwright for JavaScript-rendering:

  # I spider-koden
  use_playwright_listings = True  # For listesider
  use_playwright_items = True     # For annonse-detaljer

  Proxy-støtte

  Proxy er konfigurert i settings.py:

  HTTP_PROXY = 'http://username:password@host:port'
  HTTPS_PROXY = 'http://username:password@host:port'

  Aktiveres per spider ved behov.

  Feilhåndtering

  - Automatisk retry: Scrapy håndterer midlertidige feil
  - Errback: Custom error handler lukker Playwright-pages korrekt
  - Logging: Alle feil logges til sibr-market-scraping.log

  Testing

  Kjør tester med pytest:

  # Alle tester
  pytest tests/

  # Spesifikk spider
  pytest tests/test_car.py

  # Med verbose output
  pytest tests/ -v

  Scrapy contract-testing er inkludert i spider-koden:

  '''
  @url https://www.finn.no/mobility/search/car?make=0.744
  @returns items 40 60
  @returns requests 1 60
  @scrapes title year km total_price url
  '''

  Docker

  Bygg og kjør med Docker:

  # Bygg image
  docker build -t finn-scraper .

  # Kjør container
  docker run -v $(pwd)/../sibr-market-xxxxx.json:/app/credentials.json \
    -e GOOGLE_APPLICATION_CREDENTIALS=/app/credentials.json \
    finn-scraper --spiders cars

  Feilsøking

  Problem: "No module named 'finn_scraper'"

  Løsning: Sørg for at du kjører fra scraping-mappen.

  Problem: "Could not find credentials"

  Løsning:
  1. Sjekk at .env-filen eksisterer i parent-mappen
  2. Verifiser at GOOGLE_APPLICATION_CREDENTIALS peker til riktig fil
  3. Sjekk at service account har BigQuery-tilgang

  Problem: Playwright timeout

  Løsning:
  1. Øk timeout i finn_base.py: PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT
  2. Kjør playwright install på nytt
  3. Sjekk nettverksforbindelse

  Problem: BigQuery write errors

  Løsning:
  1. Verifiser dataset raw eksisterer i sibr-market
  2. Sjekk at service account har BigQuery Data Editor rolle
  3. Reduser BQ_BATCH_SIZE hvis minneproblemer

  Problem: Høy NaN-rate

  Systemet sender automatisk email-varsel hvis kritiske felter har >80% NaN. Sjekk:
  1. Om Finn.no har endret HTML-struktur (CSS selectors)
  2. Om Playwright trengs for JavaScript-rendering
  3. Loggfilen for detaljer: sibr-market-scraping.log

  Output og monitoring

  Logging

  Alle kjøringer logges til:
  - Console: Real-time output
  - Fil: sibr-market-scraping.log
  - Google Cloud Logging: Hvis aktivert med --cloud_logging

  BigQuery data

  Data skrives til:
  sibr-market.raw.[table_name]

  Hver rad inneholder:
  - scrape_date: Dato for scraping (DATE)
  - Alle felt fra respektive Item-klasser (STRING, konvertert automatisk)

  NaN rapport

  Ved slutten av hver spider-kjøring:

  NaN Report:
  total: 0 NaN         0.0%
  dealer_rating: 4500 NaN   45.0%
  last_eu: 1200 NaN        12.0%
  ...

  Email sendes automatisk for kritiske felter med høy NaN-rate.

  Best practices

  1. Test lokalt først: Kjør med --spiders og begrenset antall URLs
  2. Monitor BigQuery kostnader: Batch-størrelse påvirker write-operasjoner
  3. Respekter robots.txt: ROBOTSTXT_OBEY = True er aktivert
  4. Bruk custom URLs for testing: Unngå å scrape hele Finn.no under utvikling
  5. Sjekk NaN-rapporter: Identifiser manglende data tidlig
  6. Hold dependencies oppdatert: pip-compile requirements.in

  Ytelse

  - Concurrent requests: 32 samtidige
  - Batch size: 5000 items per BigQuery write
  - Playwright: Kun når nødvendig (JavaScript-tunge sider)
  - Gjennomsnitt: ~500-1000 annonser per minutt (avhengig av spider)

  Vedlikehold

  Oppdatere CSS selectors

  Hvis Finn.no endrer struktur, oppdater selectors i respektive spiders:

  # Eksempel fra car.py
  item['title'] = response.css('h1.t1::text').get()

  Test med Scrapy shell:

  scrapy shell 'https://www.finn.no/car/used/ad.html?finnkode=xxxxx' -s ITEM_PIPELINES={}

  Legge til nye spiders

  1. Opprett ny spider i finn_scraper/spiders/
  2. Arv fra FinnBaseSpider
  3. Definer Item i items.py
  4. Legg til i map_spiders i main.py
  5. Opprett test i tests/

  Lisens og ansvar

  Dette prosjektet er for internt bruk. Respekter Finn.nos bruksvilkår og robots.txt. Ikke overbelast serverne med for mange requests.