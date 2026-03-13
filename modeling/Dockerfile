FROM python:3.11-slim
LABEL authors="sigvardbratlie"
WORKDIR /app
COPY modeling/requirements.txt .

RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt
COPY modeling/ .

ENTRYPOINT ["python", "main.py"]
CMD []
