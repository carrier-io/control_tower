FROM python:3.7-alpine

RUN apk update && apk add --no-cache git bash py-pip openssl ca-certificates py-openssl wget \
    --virtual build-dependencies libffi-dev openssl-dev python-dev build-base

RUN pip install --upgrade pip
RUN pip install --upgrade setuptools

ADD setup.py /tmp/setup.py
ADD requirements.txt /tmp/requirements.txt
RUN pip install git+https://github.com/celery/celery.git
RUN pip install git+https://github.com/carrier-io/perfreporter.git
COPY control_tower /tmp/control_tower

RUN cd /tmp && mkdir /tmp/reports && python setup.py install && \
    rm -rf /tmp/control_tower /tmp/requirements.txt /tmp/setup.py

ADD run.sh /bin/run.sh
RUN chmod +x /bin/run.sh
COPY config.yaml /tmp/

SHELL ["/bin/bash", "-c"]

ENTRYPOINT ["run.sh"]