FROM python:3
ENV PYTHONUNBUFFERED 1
RUN mkdir /src
WORKDIR /src
COPY ./ /src
EXPOSE 8024
RUN pip install -r requirements.txt