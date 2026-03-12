from google.cloud import bigquery
import pandas as pd
from itemadapter import ItemAdapter
import os

# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: https://docs.scrapy.org/en/latest/topics/item-pipeline.html


# useful for handling different item types with a single interface

import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)

class Emailer:
    def __init__(self, to_address, from_address, password):
        self.to_address = to_address
        self.from_address = from_address
        self.password = password

    def send_email(self, subject, body):
        msg = MIMEMultipart()
        msg['From'] = self.from_address
        msg['To'] = self.to_address
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        try:
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login(self.from_address, self.password)
            text = msg.as_string()
            server.sendmail(self.from_address, self.to_address, text)
            server.quit()
            logger.info("✅ Email sent successfully")
        except Exception as e:
            logger.error(f"❌ Failed to send email: {e}")

emailer = Emailer(
            to_address="sigvard@sibr.no",
            from_address="sigvard.bratlie@gmail.com",
            password = os.getenv("GMAIL_PASSWORD"))

unimportant_map = {
                "cars" : [
                        "total", 
                        'prev_owners',
                        'last_eu',
                        'battery',
                        'dealer_rating',
                        'dealer_n_ratings',
                        'fuel_cons',
                        'length',
                        'height',
                        'width',
                        'condition',
                        'manufacturer',
                        'emission_class',
                        'emission_sticker',
                        'service_history',
                        'service_book',
                        'vat_deductible',
                        "gearbox_type",
                        "condition_report",],
 "homes" :      ["total",
               'collective_assets',
                'sold',
                'primary_area',
                'dealer_rating',
                'dealer_n_ratings',
                'seller_insurance',
                'plot'],
"boats" : ["total",
               'underoverskrift',
                'lengde_cm',
                'lystall',
                #'reg_num',
                'referanse',
                'dealer_rating',
                'dealer_n_ratings'],
"jobs" : ["total", 
            'positions_available',
            'dealer',
            'dealer_rating',
            'dealer_n_ratings'],
"mcs" : ["total",
         'condition_report',
            'dealer_rating',
            'dealer_n_ratings',
            'battery',
            'range',
            'manufacturer',
            'height',
            'length',
            'width',
            'sales_type',
            'first_registration',
            'last_eu',
            'next_eu',
            'warranty_until',
            'warranty_length',
            'service_history',
            'service_book'],
"rentals" : ["total",'usable_area',
            'internal_area',
            'external_area',
            'gross_area',
            'email',
            'contact_person',
            'web',
            'dealer_rating',
            'dealer_n_ratings',
            'balcony',
            'plot_size',
            'build_year',
            'energy_rating'],
"new_homes" : ["total",
                'collective_assets',
                'tax_value',
                'ownership_type',
                'build_year',
                'energy_rating',
                'primary_area',
                'plot_size',
                'plot',
                'seller_insurance']
 }

class FinnScraperPipeline:
    def process_item(self, item, spider):
        return item


class BQPipeline:
    def __init__(self,project,batch_size=100):
        #self.bq_path = bq_path
        self.batch_size = batch_size
        self.project = project
        self.buffer = []
        self._nan = {}
        self._nan['total'] = 0

    @classmethod
    def from_crawler(cls,crawler):
        return cls(
            batch_size = crawler.settings.getint('BQ_BATCH_SIZE',2500),
            project = crawler.settings.get('GOOGLE_CLOUD_PROJECT')
        )

    def open_spider(self,spider):
        spider.logger.info('🚀 BQ Pipeline started')
        self.client = bigquery.Client(project=self.project)
        self.dataset_id = f'raw'
        self.table_id = f"{self.dataset_id}.{spider.table_name}"
        spider.logger.info(f'📋 Project: {self.project} | Table: {self.table_id}')


    def close_spider(self,spider):
        if self.buffer:
            for item in self.buffer:
                self.track_nan(item)
            self._save_to_bq(spider)
        self.client.close()
        self.send_nan_report(spider)
        spider.logger.info('✅ BQ Pipeline finished')

    def track_nan(self, item):
        for key, value in item.items():
            if key not in self._nan:
                self._nan[key] = 0
            if value is None:
                self._nan[key] += 1

    def send_nan_report(self, spider):
        if not self._nan:
            return
        nan = dict(sorted(self._nan.items(), key=lambda x: x[1], reverse=True))
        report = "NaN Report:\n"
        # report += f"Total number of items: {self._nan['total']}\n"
        for key, count in nan.items():
            if key != "total" and self._nan['total'] > 0:
                report += f"{key}: {count} NaN \t {(count/self._nan['total'])*100}% \n"
                if key not in unimportant_map.get(spider.table_name, []) and (count/self._nan['total']) > 0.9:
                    subject = f"High NaN Alert: {key} in {spider.table_name}"
                    body = f"The field '{key}' has a high NaN rate of {(count/self._nan['total'])*100:.2f}% in the '{spider.table_name}' table."
                    emailer.send_email(subject, body)
            else:
                spider.logger.info(f'⚠️ Total is 0, skipping NaN% for "{key}" (count: {count})')
        spider.logger.info(report)
        self._nan.clear()

    def process_item(self, item, spider):
        self.buffer.append(ItemAdapter(item).asdict())
        self._nan['total'] += 1
        if len(self.buffer) >= self.batch_size:
            for item in self.buffer:
                self.track_nan(item)
            # spider.logger.info('Buffer size reached, saving to BigQuery...')
            self._save_to_bq(spider)
        return item
    
    def _save_to_bq(self,spider):
        if not self.buffer:
            return

        try:
            df = pd.DataFrame(self.buffer)
            for col in df.columns:
                if col != "scrape_date":
                    df[col] = df[col].astype(str)
            df["scrape_date"] = pd.to_datetime(df["scrape_date"]).dt.date
            job_config = bigquery.LoadJobConfig(
                write_disposition="WRITE_APPEND",
                schema = [bigquery.SchemaField("scrape_date", "DATE")],
                autodetect=True,

            )
            job = self.client.load_table_from_dataframe(df,self.table_id,job_config=job_config)
            job.result()
            spider.logger.info(f"📤 {len(df)} rows saved to {self.table_id}")
        except Exception as e:
            spider.logger.error(f"❌ Error saving to BigQuery: {e}")

        self.buffer.clear()
