FROM python:3.12-slim
LABEL authors="sigvardbratlie"

WORKDIR /app
COPY api/requirements.txt .

RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt
COPY api/ .
COPY bigquery-helper/src/bigquery_helper/bigquery_helper.py src/api/helpers/bigquery.py

ENTRYPOINT ["python", "main.py"]
CMD ["--task","all"]
