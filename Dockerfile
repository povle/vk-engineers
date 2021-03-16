FROM python:3.8.8-slim-buster

WORKDIR /usr/src/app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src src
COPY config config

WORKDIR /usr/src/app/src

EXPOSE 8000
CMD ["gunicorn", "--bind=0.0.0.0:8000", "--worker-class=gevent", "--worker-connections=1000", "--workers=1", "main:server"]
