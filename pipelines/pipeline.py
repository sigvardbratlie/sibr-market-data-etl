from kfp import dsl,compiler
from google.cloud import aiplatform
from google.cloud import storage
from dotenv import load_dotenv
import os
from pathlib import Path
import argparse


load_dotenv()
if not os.getenv('GOOGLE_APPLICATION_CREDENTIALS'):
    raise ValueError("GOOGLE_APPLICATION_CREDENTIALS environment variable is not set. Please set it to the path of your Google Cloud credentials JSON file.")

# ---- SETUP ----
PROJECT_ID = 'sibr-market'
REGION = 'europe-west1'
BUCKET_NAME = 'sibr-market'
BUCKET_URI = f'gs://{BUCKET_NAME}'
REPO = 'sibr-market-repo'

parser = argparse.ArgumentParser()
parser.add_argument("--commit-sha", type = str, help = "The git commit SHA to use for the image tag")
parser.add_argument("--tag-scraping", type = str,)
parser.add_argument("--tag-api",type = str)
parser.add_argument("--tag-modeling",type = str)
parser.add_argument("--tag-cadastral",type = str)
parser.add_argument("--run",action = "store_true",help = "Run the pipeline")
parser.add_argument("--skip-schedule", action = "store_true", help = "Skip creating a schedule")

args = parser.parse_args()
TAG = args.commit_sha if args.commit_sha else 'latest'


image_tags = {"scraping": args.tag_scraping if args.tag_scraping else TAG,
              "api" : args.tag_api if args.tag_api else TAG,
              "modeling" : args.tag_modeling if args.tag_modeling else TAG,
              "cadastral" : args.tag_cadastral if args.tag_cadastral else TAG}

# SCRAPING_IMAGE_URI = f"{REGION}-docker.pkg.dev/{PROJECT_ID}/{REPO}/scraping:{TAG}"
# API_IMAGE_URI = f"{REGION}-docker.pkg.dev/{PROJECT_ID}/{REPO}/api:{TAG}"
# MODELING_IMAGE_URI = f"{REGION}-docker.pkg.dev/{PROJECT_ID}/{REPO}/modeling:{TAG}"
# CADASTRAL_IMAGE_URI = f"{REGION}-docker.pkg.dev/{PROJECT_ID}/{REPO}/cadastral:{TAG}"

def mk_image_uri(task : str):
    return f"{REGION}-docker.pkg.dev/{PROJECT_ID}/{REPO}/{task}:{image_tags[task]}"

@dsl.container_component
def run_scraping():
    return dsl.ContainerSpec(
        image=mk_image_uri("scraping"),
        command=['python', 'main.py'],
    )

@dsl.container_component
def run_api(): # Endret
    return dsl.ContainerSpec(
        image=mk_image_uri("api"),
        command=['python', 'main.py'],
        args = ["--task", "all"]
    )

@dsl.container_component
def run_predict(): # Endret
    return dsl.ContainerSpec(
        image=mk_image_uri("modeling"),
        command=['python', 'main.py'],
        args=['--run-predict']
    )

@dsl.container_component
def run_clean(): # Endret
    return dsl.ContainerSpec(
        image=mk_image_uri("modeling"),
        command=['python', 'main.py'],
        args=['--run-clean']
    )

@dsl.container_component
def run_cadastral(): # Endret
    return dsl.ContainerSpec(
        image=mk_image_uri("cadastral"),
        command=['python', 'main.py'],
        args = ["-up", "-s","-ow"]
    )

# ---- PIPELINE DEFINITION ----
@dsl.pipeline(
    name='sibr-market-pipeline',
    description='Pipeline for scraping, api, and cleaning/predicting data for SIBR Market',
    pipeline_root=BUCKET_URI
)
def create_pipeline(
):
    # Step 1: Run scraping
    scraping_task = run_scraping()
    scraping_task.set_display_name('1. Scraping Data')
    scraping_task.set_caching_options(False)

    # Step 2: Run cleaning
    #cleaning_task = run_clean()
    cleaning_task = run_clean().after(scraping_task)
    cleaning_task.set_display_name('2. Cleaning Data')
    cleaning_task.set_caching_options(False)

    # Step 3: Run api
    #api_task = run_api()
    api_task = run_api().after(cleaning_task)
    api_task.set_display_name('3. API step')
    api_task.set_caching_options(False)

    # Step 4: Run cadastral
    cadastral_task = run_cadastral().after(api_task)
    cadastral_task.set_display_name('4. Get cadastral data')
    cadastral_task.set_caching_options(False)

    # # Step 4: Run cleaning and prediction
    # clean_predict_task = run_predict().after(geocoding_task)
    # clean_predict_task.set_display_name('4. Predict Data')
    # clean_predict_task.set_caching_options(False)

if __name__ == '__main__':
    PIPELINE_JSON = 'sibr-market-pipeline.json'
    compiler.Compiler().compile(
        pipeline_func=create_pipeline,
        package_path=PIPELINE_JSON
    )

    aiplatform.init(project=PROJECT_ID,
                    location=REGION,
                    service_account="pipeline@sibr-market.iam.gserviceaccount.com")
    job = aiplatform.PipelineJob(
        display_name='sibr-market-pipeline',
        template_path=PIPELINE_JSON,
        pipeline_root=BUCKET_URI,
    )

    if not args.skip_schedule:
        client = storage.Client()
        bucket = client.get_bucket(BUCKET_NAME)
        blob = bucket.blob(PIPELINE_JSON)
        blob.upload_from_filename(PIPELINE_JSON)

        job_schedule = job.create_schedule(
            display_name="run-sibr-market-pipeline",
            cron = "0 2 */3 * *",
            max_concurrent_run_count = 1,
        )
        print(f'Created schedule: {job_schedule.name}')

    if args.run:
        print(f'Starting the first run immediately')
        job.run()
        print(f'Finished starting the first run')