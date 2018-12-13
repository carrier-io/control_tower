FROM python:3.6-alpine

RUN apk update && apk add --no-cache git

RUN pip install --upgrade pip
RUN pip install --upgrade setuptools
RUN pip install git+https://github.com/celery/celery.git

ADD setup.py /tmp/setup.py
ADD requirements.txt /tmp/requirements.txt
COPY control_tower /tmp/control_tower

RUN cd /tmp && python setup.py install && rm -rf /tmp/control_tower /tmp/requirements.txt /tmp/setup.py


ENTRYPOINT ["run"]