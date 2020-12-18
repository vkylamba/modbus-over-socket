FROM python:3.8

RUN mkdir app

WORKDIR /app

COPY requirements.txt /app
RUN pip install -r requirements.txt

COPY . /app

EXPOSE 8024
ENTRYPOINT ["sh", "start_server.sh"]
