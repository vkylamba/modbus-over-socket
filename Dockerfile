FROM registry.opensource.zalan.do/stups/python:3.6.5-22

RUN mkdir app

WORKDIR /app

COPY ./api_logger /app/
COPY ./delta /app/
COPY ./modbus /app/
COPY ./utils /app/
COPY ./*.py /app/
COPY ./*.json /app/
COPY ./*.sh /app/
COPY ./*.txt /app/

RUN pip install -r requirements.txt
ENTRYPOINT ["sh", "start_server.sh"]
