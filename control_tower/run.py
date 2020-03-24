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

from copy import deepcopy
from json import loads, dumps
from os import environ, path
from celery import Celery, chord
from time import sleep
from uuid import uuid4
import re
from datetime import datetime
import requests
import sys

REDIS_USER = environ.get('REDIS_USER', '')
REDIS_PASSWORD = environ.get('REDIS_PASSWORD', 'password')
REDIS_HOST = environ.get('REDIS_HOST', 'localhost')
REDIS_PORT = environ.get('REDIS_PORT', '6379')
REDIS_DB = environ.get('REDIS_DB', 1)
GALLOPER_WEB_HOOK = environ.get('GALLOPER_WEB_HOOK', None)
LOKI_HOST = environ.get('loki_host', None)
LOKI_PORT = environ.get('loki_port', '3100')
GALLOPER_URL = environ.get('galloper_url', None)
PROJECT_ID = environ.get('project_id', None)
BUCKET = environ.get('bucket', None)
TEST = environ.get('artifact', None)
ADDITIONAL_FILES = environ.get('additional_files', None)
BUILD_ID = environ.get('build_id', f'build_{uuid4()}')
DISTRIBUTED_MODE_PREFIX = environ.get('PREFIX', f'test_results_{uuid4()}_')
JVM_ARGS = environ.get('JVM_ARGS', None)
mount_source = environ.get('mount_source', None)
mount_target = environ.get('mount_target', None)
release_id = environ.get('release_id', None)
app = None
JOB_TYPE_MAPPING = {
    "perfmeter": "jmeter",
    "perfgun": "gatling",
    "free_style": "other"
}


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
    parser.add_argument('-c', '--container', action="append", type=str,
                        help="Name of container to run the job e.g. getcarrier/dusty:latest")
    parser.add_argument('-e', '--execution_params', action="append", type=str2json,
                        help="Execution params for jobs e.g. \n"
                             "{\n\t'host': 'localhost', \n\t'port':'443', \n\t'protocol':'https'"
                             ", \n\t'project_name':'MY_PET', \n\t'environment':'stag', \n\t"
                             "'test_type': 'basic'"
                             "\n} will be valid for dast container")
    parser.add_argument('-t', '--job_type', action="append", type=str,
                        help="Type of a job: e.g. sast, dast, perfmeter, perfgun, perf-ui")
    parser.add_argument('-n', '--job_name', type=str, default='',
                        help="Name of a job (e.g. unique job ID, like %JOBNAME%_%JOBID%)")
    parser.add_argument('-q', '--concurrency', action="append", type=int,
                        help="Number of parallel workers to run the job")
    parser.add_argument('-r', '--channel', action="append", default=[], type=int,
                        help="Number of parallel workers to run the job")
    parser.add_argument('-a', '--artifact', action="append", default="", type=str)
    parser.add_argument('-b', '--bucket', action="append", default="", type=str)
    parser.add_argument('-sr', '--save_reports', action="append", default=None, type=str)
    parser.add_argument('-j', '--junit', default=False, type=str2bool)
    parser.add_argument('-qg', '--quality_gate', default=False, type=str2bool)
    parser.add_argument('-p', '--report_path', default="/tmp/reports", type=str)
    args, _ = parser.parse_known_args()
    return args


def parse_id():
    parser = argparse.ArgumentParser(description='Carrier Command Center')
    parser.add_argument('-g', '--groupid', type=str, default="", help="ID of the group for a task")
    parser.add_argument('-c', '--container', type=str, help="Name of container to run the job "
                                                            "e.g. getcarrier/dusty:latest")
    parser.add_argument('-t', '--job_type', type=str, help="Type of a job: e.g. sast, dast, perf-jmeter, perf-ui")
    parser.add_argument('-n', '--job_name', type=str, help="Name of a job (e.g. unique job ID, like %JOBNAME%_%JOBID%)")
    args, _ = parser.parse_known_args()
    if args.groupid:
        for unparsed in _:
            args.groupid = args.groupid + unparsed
    if 'group_id' in args.groupid:
        args.groupid = loads(args.groupid)
    return args


def connect_to_celery(concurrency, redis_db=None):
    # global app
    if not (redis_db and isinstance(redis_db, int)):
        redis_db = REDIS_DB
    # if not app or redis_db not in app:
    app = Celery('CarrierExecutor',
                 broker=f'redis://{REDIS_USER}:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/{redis_db}',
                 backend=f'redis://{REDIS_USER}:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/{redis_db}',
                 include=['celery'])

    print(f"Celery Status: {dumps(app.control.inspect().stats(), indent=2)}")
    if concurrency:
        workers = sum(value['pool']['max-concurrency'] for key, value in app.control.inspect().stats().items())
        active = sum(len(value) for key, value in app.control.inspect().active().items())
        available = workers - active
        print(f"Total Workers: {workers}")
        print(f"Available Workers: {available}")
        if workers < concurrency:
            print(f"We are unable to process your request due to limited resources. We have {workers} available")
            exit(1)
    return app


def start_job(args=None):
    if not args:
        args = arg_parse()
    concurrency_cluster = {}
    channels = args.channel
    if not channels:
        for _ in args.container:
            channels.append(REDIS_DB)
    for index in range(len(channels)):
        if str(channels[index]) not in concurrency_cluster:
            concurrency_cluster[str(channels[index])] = 0
        concurrency_cluster[str(channels[index])] += args.concurrency[index]
    celery_connection_cluster = {}
    results_bucket = str(args.job_name).replace("_", "").lower()
    post_processor_args = {
        "galloper_url": GALLOPER_URL,
        "project_id": PROJECT_ID,
        "galloper_web_hook": GALLOPER_WEB_HOOK,
        "bucket": results_bucket,
        "prefix": DISTRIBUTED_MODE_PREFIX,
        "junit": args.junit
    }
    for channel in channels:
        if str(channel) not in celery_connection_cluster:
            celery_connection_cluster[str(channel)] = {}
        celery_connection_cluster[str(channel)]['app'] = connect_to_celery(concurrency_cluster[str(channel)], channel)
        celery_connection_cluster[str(channel)]['post_processor'] = \
            celery_connection_cluster[str(channel)]['app'].signature('tasks.post_process', kwargs=post_processor_args)
    job_type = "".join(args.container)
    job_type += "".join(args.job_type)

    for i in range(len(args.container)):
        if 'tasks' not in celery_connection_cluster[str(channels[i])]:
            celery_connection_cluster[str(channels[i])]['tasks'] = []
        exec_params = deepcopy(args.execution_params[i])

        if args.job_type[i] in ['perfgun', 'perfmeter']:
            if path.exists('/tmp/config.yaml'):
                with open('/tmp/config.yaml', 'r') as f:
                    config_yaml = f.read()
                exec_params['config_yaml'] = dumps(config_yaml)
            else:
                exec_params['config_yaml'] = {}
            if LOKI_HOST:
                exec_params['loki_host'] = LOKI_HOST
                exec_params['loki_port'] = LOKI_PORT
            if ADDITIONAL_FILES:
                exec_params['additional_files'] = ADDITIONAL_FILES
            if JVM_ARGS:
                exec_params['JVM_ARGS'] = JVM_ARGS
            if mount_source:
                exec_params['mount_source'] = mount_source
            if mount_target:
                exec_params['mount_target'] = mount_target

            exec_params['build_id'] = BUILD_ID
            exec_params['DISTRIBUTED_MODE_PREFIX'] = DISTRIBUTED_MODE_PREFIX
            exec_params['galloper_url'] = GALLOPER_URL
            exec_params['bucket'] = BUCKET if not args.bucket else args.bucket[i]
            exec_params['artifact'] = TEST if not args.artifact else args.artifact[i]
            exec_params['results_bucket'] = results_bucket
            exec_params['save_reports'] = args.save_reports
            if PROJECT_ID:
                exec_params['project_id'] = PROJECT_ID

        for _ in range(int(args.concurrency[i])):
            task_kwargs = {'job_type': str(args.job_type[i]), 'container': args.container[i],
                           'execution_params': exec_params, 'redis_connection': '',  'job_name': args.job_name}
            celery_connection_cluster[str(channels[i])]['tasks'].append(
                celery_connection_cluster[str(channels[i])]['app'].signature('tasks.execute', kwargs=task_kwargs))

    groups = []
    for each in celery_connection_cluster:
        task_group = chord(celery_connection_cluster[each]['tasks'],
                           app=celery_connection_cluster[each]['app'])(
            celery_connection_cluster[each]['post_processor'])
        groups.append(task_group)

    test_start_notify(args)
    #     group_id = task_group.apply_async()
    #     group_id.save()
    #     group_ids[each] = {"group_id": group_id.id}
    # print(f"Group IDs: {dumps(group_ids)}")

    # with open('/tmp/_taskid', 'w') as f:
    #     f.write(dumps(group_ids))
    return groups


def test_start_notify(args):
    if GALLOPER_URL:
        vusers_var_names = ["vusers", "users", "users_count", "ramp_users", "user_count"]
        lg_type = JOB_TYPE_MAPPING.get(args.job_type[0], "other")
        if lg_type == 'jmeter':
            exec_params = args.execution_params[0]['cmd'] + " "
            test_type = re.findall('-Jtest.type=(.+?) ', exec_params)
            test_type = test_type[0] if len(test_type) else 'demo'
            environment = re.findall("-Jenv.type=(.+?) ", exec_params)
            environment = environment[0] if len(environment) else 'demo'
            test_name = re.findall("-Jtest_name=(.+?) ", exec_params)
            test_name = test_name[0] if len(test_name) else 'test'
            duration = re.findall("-JDURATION=(.+?) ", exec_params)
            duration = float(duration[0]) if len(duration) else 0
            vusers = 0
            for each in vusers_var_names:
                if f'-j{each}' in exec_params.lower():
                    pattern = f'-j{each}=(.+?) '
                    vusers = re.findall(pattern, exec_params.lower())
                    vusers = int(vusers[0]) * args.concurrency[0]
                    break
        elif lg_type == 'gatling':
            exec_params = args.execution_params[0]
            test_type = exec_params['test_type'] if exec_params.get('test_type') else 'demo'
            test_name = exec_params['test'].split(".")[1].lower() if exec_params.get('test') else 'test'
            environment = exec_params['env'] if exec_params.get('env') else 'demo'
            duration, vusers = 0, 0
            if exec_params.get('GATLING_TEST_PARAMS'):
                if '-dduration' in exec_params['GATLING_TEST_PARAMS'].lower():
                    duration = re.findall("-dduration=(.+?) ", exec_params['GATLING_TEST_PARAMS'].lower())[0]
                for each in vusers_var_names:
                    if f'-d{each}' in exec_params['GATLING_TEST_PARAMS'].lower():
                        pattern = f'-d{each}=(.+?) '
                        vusers = re.findall(pattern, exec_params['GATLING_TEST_PARAMS'].lower())
                        vusers = int(vusers[0]) * args.concurrency[0]
                        break
        else:
            return
        start_time = datetime.utcnow().isoformat("T") + "Z"

        data = {'build_id': BUILD_ID, 'test_name': test_name, 'lg_type': lg_type, 'type': test_type,
                'duration': duration, 'vusers': vusers, 'environment': environment, 'start_time': start_time,
                'missed': 0}
        if release_id:
            data['release_id'] = release_id
        headers = {'content-type': 'application/json'}
        if PROJECT_ID:
            url = f'{GALLOPER_URL}/api/v1/reports/{PROJECT_ID}'
        else:
            url = f'{GALLOPER_URL}/api/report'
        r = requests.post(url, json=data, headers=headers)
        print(r.text)


def start_job_exec(args=None):
    start_job(args)
    exit(0)


def check_ready(result):
    if result and not result.ready():
        return False
    return True


# TODO check for lost connection and retry
def track_job(group):
    while not group.ready():
        sleep(30)
        print("Still processing ... ")
    if group.successful():
        print("We are done successfully")
    else:
        print("We are failed badly")
    group.forget()
    # if not args:
    #     args = parse_id()
    # if not group_id:
    #     group_id = args.groupid
    # for id in group_id:
    #     group_id[id]['app'] = connect_to_celery(0, redis_db=int(id))
    #     group_id[id]['result'] = GroupResult.restore(group_id[id]['group_id'], app=group_id[id]['app'])
    # while not all(check_ready(group_id[id]['result']) for id in group_id):
    #     sleep(30)
    #     print("Still processing ... ")
    # if all(check_ready(group_id[id]['result']) for id in group_id):
    #     print("We are done successfully")
    # else:
    #     print("We are failed badly")
    #     if retry:
    #         print(f"Retry for GroupID: {group_id}")
    #         return track_job(group_id=group_id, retry=False)
    #     else:
    #         return "Failed"
    # for id in group_id:
    #     print(group_id)
    #     for each in group_id[id]['result'].get():
    #         print(each)

    return "Done"


def track_job_exec(args=None):
    track_job(args)
    exit(0)


def start_and_track(args=None):
    if not args:
        args = arg_parse()
    groups = start_job(args)
    print("Job started, waiting for containers to settle ... ")
    for group in groups:
        track_job(group)
    if args.junit:
        process_junit_report(args)
    exit(0)


def process_junit_report(args):
    file_name = "junit_report_{}.xml".format(DISTRIBUTED_MODE_PREFIX)
    results_bucket = str(args.job_name).replace("_", "").lower()
    junit_report = download_junit_report(results_bucket, file_name, retry=12)
    if junit_report:
        with open("{}/{}".format(args.report_path, file_name), "w") as f:
            f.write(junit_report.text)

        failed = int(re.findall("testsuites .+? failures=\"(.+?)\"", junit_report.text)[0])
        total = int(re.findall("testsuites .+? tests=\"(.+?)\"", junit_report.text)[0])
        errors = int(re.findall("testsuites .+? errors=\"(.+?)\"", junit_report.text)[0])
        skipped = int(re.findall("testsuite .+? skipped=\"(.+?)\"", junit_report.text)[0])
        print("**********************************************")
        print("* Performance testing jUnit report | Carrier *")
        print("**********************************************")
        print(f"Tests run: {total}, Failures: {failed}, Errors: {errors}, Skipped: {skipped}")
        if args.quality_gate:
            rate = round(float(failed / total) * 100, 2) if total != 0 else 0
            if rate > 20:
                print("Missed threshold rate is {}".format(rate), file=sys.stderr)
                exit(1)


def download_junit_report(results_bucket, file_name, retry):
    if PROJECT_ID:
        url = f'{GALLOPER_URL}/api/v1/artifacts/{PROJECT_ID}/{results_bucket}/{file_name}'
    else:
        url = f'{GALLOPER_URL}/artifacts/{results_bucket}/{file_name}'
    junit_report = requests.get(url, allow_redirects=True)
    if 'botocore.errorfactory.NoSuchKey' in junit_report.text:
        retry -= 1
        if retry == 0:
            return None
        sleep(10)
        return download_junit_report(results_bucket, file_name, retry)
    return junit_report


def kill_job(args=None, group_id=None):
    # if not args:
    #     args = parse_id()
    # if not group_id:
    #     group_id = args.groupid
    # if not group_id:
    #     with open("/tmp/_taskid", "r") as f:
    #         group_id = loads(f.read().strip())
    # for id in group_id:
    #     group_id[id]['app'] = connect_to_celery(0, redis_db=int(id))
    #     group_id[id]['result'] = GroupResult.restore(group_id[id]['group_id'], app=group_id[id]['app'])
    #     group_id[id]['task_id'] = []
    #     if not group_id[id]['result'].ready():
    #         abortable_result = []
    #         for task in group_id[id]['result'].children:
    #             group_id[id]['task_id'].append(task.id)
    #             abortable_id = AbortableAsyncResult(id=task.id, parent=group_id[id]['result'].id,
    #                                                 app=group_id[id]['app'])
    #             abortable_id.abort()
    #             abortable_result.append(abortable_id)
    #         if abortable_result:
    #             while not all(res.result for res in abortable_result):
    #                 sleep(5)
    #                 print("Aborting distributed tasks ... ")
    # print("Group aborted ...")
    # print("Verifying that tasks aborted as well ... ")
    # # This process is to handle a case when parent is canceled, but child have not
    # for id in group_id:
    #     i = inspect(app=group_id[id]['app'])
    #     tasks_list = []
    #     for tasks in [i.active(), i.scheduled(), i.reserved()]:
    #         for node in tasks:
    #             if tasks[node]:
    #                 tasks_list.append(task['id'] for task in tasks[node])
    #     abortable_result = []
    #     for task_id in group_id[id]['task_id']:
    #         if task_id in tasks_list:
    #             abortable_id = AbortableAsyncResult(id=task_id, app=group_id[id]['app'])
    #             abortable_id.abort()
    #             abortable_result.append(abortable_id)
    #     if abortable_result:
    #         while not all(res.result for res in abortable_result):
    #             sleep(5)
    #             print("Aborting distributed tasks ... ")
    exit(0)


# if __name__ == "__main__":
#     from control_tower.config_mock import BulkConfig
#     start_and_track(args=BulkConfig())
#     # group_id = start_job(config)
#     # print(group_id)
#     # track_job(group_id=group_id)
#     # kill_job(config)
#     # track_job(group_id='73331467-20ee-4d53-a570-6cd0296779aa')
#     pass

