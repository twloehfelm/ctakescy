FROM python:3.8-slim-buster

WORKDIR /app

# set env variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

COPY ./requirements.txt /app/requirements.txt

COPY ./app /app

RUN \
    apt-get update \
    && apt-get -y install libpq-dev gcc \
    && pip install --no-deps --no-cache-dir -r requirements.txt 

# These were failing if added to the same requirements.txt file
# They need cython to be installed and available first I think.
RUN \ 
     pip install PyRuSH==1.0.3.5 \
     && pip install quicksectx==0.3.0 \
     && pip install python-multipart==0.0.5
