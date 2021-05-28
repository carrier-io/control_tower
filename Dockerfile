FROM python:3.7-alpine

RUN apk update && apk add --no-cache git bash

RUN pip install --upgrade pip
RUN pip install --upgrade setuptools
RUN pip install --upgrade 'requests==2.20.0'

ENV CRYPTOGRAPHY_DONT_BUILD_RUST=1

RUN apk add --no-cache --virtual .build-deps gcc musl-dev libffi-dev openssl-dev python3-dev make
RUN pip install dulwich==0.19.11
RUN pip install paramiko==2.6.0
RUN pip install boto3==1.17.34
RUN apk del .build-deps gcc musl-dev libffi-dev openssl-dev python3-dev make
RUN pip install git+https://github.com/carrier-io/arbiter.git@v.2.5
ADD setup.py /tmp/setup.py
ADD requirements.txt /tmp/requirements.txt
COPY control_tower /tmp/control_tower
RUN cd /tmp && mkdir /tmp/reports && python setup.py install && \
    rm -rf /tmp/control_tower /tmp/requirements.txt /tmp/setup.py
ENV PYTHONUNBUFFERED=1
ADD run.sh /bin/run.sh
RUN chmod +x /bin/run.sh
COPY config.yaml /tmp/
SHELL ["/bin/bash", "-c"]

ENTRYPOINT ["run.sh"]
