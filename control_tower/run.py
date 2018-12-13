#  Copyright (c) 2018 getcarrier.io
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

import argparse
from json import loads
from os import environ
from celery import Celery, group
from time import sleep

REDIS_USER = environ.get('REDIS_USER', '')
REDIS_PASSWORD = environ.get('REDIS_PASSWORD', 'password')
REDIS_HOST = environ.get('REDIS_HOST', 'localhost')
REDIS_PORT = environ.get('REDIS_PORT', '6379')
REDIS_DB = environ.get('REDIS_DB', 1)


def str2bool(v):
    if v.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    elif v.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError('Boolean value expected.')


def str2json(v):
    try:
        return loads(v)
    except:
        raise argparse.ArgumentTypeError('Json is not properly formatted.')


def arg_parse():
    parser = argparse.ArgumentParser(description='Carrier Command Center')
    parser.add_argument('-c', '--container', type=str, help="Name of container to run the job "
                                                            "e.g. getcarrier/dusty:latest")
    parser.add_argument('-e', '--execution_params', type=str2json,
                        help="Execution params for jobs e.g. \n"
                             "{\n\t'host': 'localhost', \n\t'port':'443', \n\t'protocol':'https'"
                             ", \n\t'project_name':'MY_PET', \n\t'environment':'stag', \n\t"
                             "'test_type': 'basic'"
                             "\n} will be valid for dast container")
    parser.add_argument('-t', '--job_type', type=str, help="Type of a job: e.g. sast, dast, perf-jmeter, perf-ui")
    parser.add_argument('-n', '--job_name', type=str, help="Name of a job (e.g. unique job ID, like %JOBNAME%_%JOBID%)")
    parser.add_argument('-q', '--concurrency', type=int, default=1, help="Number of parallel workers to run the job")
    return parser.parse_args()


def main():
    args = arg_parse()
    app = Celery('CarrierExecutor',
                 broker=f'redis://{REDIS_USER}:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}',
                 backend=f'redis://{REDIS_USER}:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}',
                 include=['celery'])
    workers = 0
    available = 0
    stats = app.control.inspect().stats()
    for interceptor in stats.values():
        print(interceptor)
        workers += interceptor['pool']['writes']['inqueues']['total']
        available += interceptor['pool']['writes']['inqueues']['total'] \
                     - interceptor['pool']['writes']['inqueues']['active']
    print(f"Total Workers: {workers}")
    print(f"Available Workers: {available}")
    if workers < args.concurrency:
        return f"We are unable to process your request due to limited resources. We have {workers} available"
    tasks = [app.signature('tasks.execute',
                           kwargs={'job_type': args.job_type,
                                   'container': args.container,
                                   'execution_params': args.execution_params,
                                   'job_name': args.job_name}) for _ in range(args.concurrency)]
    task_group = group(tasks, app=app)
    result = task_group.apply_async()
    print("Starting execution")
    sleep(30)
    while not result.ready():
        sleep(30)
        print("Still processing ... ")
    if result.successful():
        # TODO: add pulling results from redis
        print("We are done successfully")
    else:
        print("We are failed badly")
    for each in result.get():
        print(each)


if __name__ == "__main__":
    main()
