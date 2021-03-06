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

import os
import tempfile
import zipfile
from arbiter import Arbiter, Task
from copy import deepcopy
from json import loads, dumps
from os import environ, path
from time import sleep, time
from uuid import uuid4
import re
from datetime import datetime
import requests
import sys

RABBIT_USER = environ.get('RABBIT_USER', 'user')
RABBIT_PASSWORD = environ.get('RABBIT_PASSWORD', 'password')
RABBIT_HOST = environ.get('RABBIT_HOST', 'localhost')
RABBIT_PORT = environ.get('RABBIT_PORT', '5672')
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
TOKEN = environ.get('token', None)
mounts = environ.get('mounts', None)
release_id = environ.get('release_id', None)
app = None
SAMPLER = environ.get('sampler', "REQUEST")
REQUEST = environ.get('request', "All")
CALCULATION_DELAY = environ.get('data_wait', 300)
CHECK_SATURATION = environ.get('check_saturation', None)
MAX_ERRORS = environ.get('error_rate', 100)
DEVIATION = environ.get('dev', 0.02)
MAX_DEVIATION = environ.get('max_dev', 0.05)
U_AGGR = environ.get('u_aggr', 1)
KILL_MAX_WAIT_TIME = 10
SPLIT_CSV = environ.get('split_csv', 'False')
CSV_PATH = environ.get('csv_path', '')
report_type = ""

JOB_TYPE_MAPPING = {
    "perfmeter": "jmeter",
    "perfgun": "gatling",
    "free_style": "other",
    "observer": "observer",
    "dast": "dast",
    "sast": "sast",
}

REPORT_TYPE_MAPPING = {
    "gatling": "backend",
    "jmeter": "backend",
    "observer": "frontend",
    "dast": "security",
    "sast": "security"
}

PROJECT_PACKAGE_MAPPER = {
    "basic": {"duration": 1800, "load_generators": 1},
    "startup": {"duration": 7200, "load_generators": 5},
    "professional": {"duration": 28800, "load_generators": 10},
    "enterprise": {"duration": -1, "load_generators": -1},
    "custom": {"duration": -1, "load_generators": -1},  # need to set custom values?
}

ENV_VARS_MAPPING = {
    "RABBIT_USER": "RABBIT_USER",
    "RABBIT_PASSWORD": "RABBIT_PASSWORD",
    "RABBIT_HOST": "RABBIT_HOST",
    "RABBIT_PORT": "RABBIT_PORT",
    "GALLOPER_WEB_HOOK": "GALLOPER_WEB_HOOK",
    "LOKI_PORT": "LOKI_PORT",
    "mounts": "mounts",
    "release_id": "release_id",
    "sampler": "SAMPLER",
    "request": "REQUEST",
    "data_wait": "CALCULATION_DELAY",
    "check_saturation": "CHECK_SATURATION",
    "error_rate": "MAX_ERRORS",
    "dev": "DEVIATION",
    "max_dev": "MAX_DEVIATION",
    "galloper_url": "GALLOPER_URL",
    "token": "TOKEN",
    "project_id": "PROJECT_ID",
    "bucket": "BUCKET",
    "u_aggr": "U_AGGR",
    "split_csv": "SPLIT_CSV",
    "csv_path": "CSV_PATH"
}


def str2bool(v):
    if isinstance(v, bool):
        return v
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
    parser.add_argument('-c', '--container', action="append", type=str, default=[],
                        help="Name of container to run the job e.g. getcarrier/dusty:latest")
    parser.add_argument('-e', '--execution_params', action="append", type=str2json, default=[],
                        help="Execution params for jobs e.g. \n"
                             "{\n\t'host': 'localhost', \n\t'port':'443', \n\t'protocol':'https'"
                             ", \n\t'project_name':'MY_PET', \n\t'environment':'stag', \n\t"
                             "'test_type': 'basic'"
                             "\n} will be valid for dast container")
    parser.add_argument('-t', '--job_type', action="append", type=str, default=[],
                        help="Type of a job: e.g. sast, dast, perfmeter, perfgun, perf-ui")
    parser.add_argument('-n', '--job_name', type=str, default="test",
                        help="Name of a job (e.g. unique job ID, like %JOBNAME%_%JOBID%)")
    parser.add_argument('-q', '--concurrency', action="append", type=int, default=[],
                        help="Number of parallel workers to run the job")
    parser.add_argument('-r', '--channel', action="append", default=[], type=str,
                        help="Rabbit (interceptor) queue name to run the job")
    parser.add_argument('-a', '--artifact', default="", type=str)
    parser.add_argument('-b', '--bucket', default="", type=str)
    parser.add_argument('-sr', '--save_reports', default=False, type=str2bool)
    parser.add_argument('-j', '--junit', default=False, type=str2bool)
    parser.add_argument('-qg', '--quality_gate', default=False, type=str2bool)
    parser.add_argument('-jr', '--jira', default=False, type=str2bool)
    parser.add_argument('-eml', '--email', default=False, type=str2bool)
    parser.add_argument('-el', '--email_recipients', default="", type=str)
    parser.add_argument('-rp', '--report_portal', default=False, type=str2bool)
    parser.add_argument('-ado', '--azure_devops', default=False, type=str2bool)
    parser.add_argument('-p', '--report_path', default="/tmp/reports", type=str)
    parser.add_argument('-d', '--deviation', default=0, type=float)
    parser.add_argument('-md', '--max_deviation', default=0, type=float)
    parser.add_argument('-tid', '--test_id', default="", type=str)
    args, _ = parser.parse_known_args()
    if args.test_id and GALLOPER_URL:
        args = append_test_config(args)
    return args


def append_test_config(args):
    headers = {'content-type': 'application/json'}
    if TOKEN:
        headers['Authorization'] = f'bearer {TOKEN}'
    url = f"{GALLOPER_URL}/api/v1/tests/{PROJECT_ID}/{args.test_id}"
    # get job_type
    test_config = requests.get(url, headers=headers).json()
    job_type = args.job_type[0] if args.job_type else test_config["job_type"]
    lg_type = JOB_TYPE_MAPPING.get(job_type, "other")
    globals()["report_type"] = lg_type
    params = {}
    execution_params = []
    concurrency = []
    container = []
    job_type = []
    tests_count = len(args.concurrency) if args.concurrency else 1
    # prepare params
    for i in range(tests_count):
        if lg_type == 'jmeter':
            url = f"{GALLOPER_URL}/api/v1/tests/{PROJECT_ID}/backend/{args.test_id}"
            if args.execution_params and "cmd" in args.execution_params[i].keys():
                exec_params = args.execution_params[i]['cmd'].split("-J")
                for each in exec_params:
                    if "=" in each:
                        _ = each.split("=")
                        params[_[0]] = str(_[1]).strip()
        elif lg_type == 'gatling':
            url = f"{GALLOPER_URL}/api/v1/tests/{PROJECT_ID}/backend/{args.test_id}"
            if args.execution_params and "GATLING_TEST_PARAMS" in args.execution_params[i].keys():
                exec_params = args.execution_params[i]['GATLING_TEST_PARAMS'].split("-D")
                for each in exec_params:
                    if "=" in each:
                        _ = each.split("=")
                        params[_[0]] = str(_[1]).strip()
        elif lg_type == 'observer':
            url = f"{GALLOPER_URL}/api/v1/tests/{PROJECT_ID}/frontend/{args.test_id}"
        elif lg_type == 'dast':
            url = f"{GALLOPER_URL}/api/v1/tests/{PROJECT_ID}/dast/{args.test_id}"
        elif lg_type == 'sast':
            url = f"{GALLOPER_URL}/api/v1/tests/{PROJECT_ID}/sast/{args.test_id}"
        else:
            print(f"No data found for test_id={args.test_id}")
            exit(1)

        data = {
            "parallel": args.concurrency[i] if args.concurrency else None,
            "params": dumps(params),
            "emails": args.email_recipients if args.email_recipients else "",
            "type": "config"
        }
        # merge params with test config
        test_config = requests.post(url, json=data, headers=headers).json()
        # set args and env vars
        execution_params.append(loads(test_config["execution_params"]))
        concurrency.append(test_config["concurrency"])
        container.append(test_config["container"])
        job_type.append(test_config["job_type"])

        for each in ["artifact", "bucket", "job_name", "email_recipients"]:
            if not getattr(args, each) and each in test_config.keys():
                setattr(args, each, test_config[each])
        for each in ["container", "job_type", "channel"]:
            if not getattr(args, each) and each in test_config.keys():
                setattr(args, each, [test_config[each]])
        for each in ["junit", "quality_gate", "save_reports", "jira", "report_portal", "email", "azure_devops"]:
            if not getattr(args, each) and each in test_config.keys():
                setattr(args, each, str2bool(test_config[each]))
        env_vars = test_config["cc_env_vars"]
        for key, value in env_vars.items():
            if not environ.get(key, None):
                globals()[ENV_VARS_MAPPING.get(key)] = value

    setattr(args, "execution_params", execution_params)
    setattr(args, "concurrency", concurrency)
    setattr(args, "container", container)
    setattr(args, "job_type", job_type)
    if "git" in test_config.keys():
        process_git_repo(test_config, args)
    if str2bool(SPLIT_CSV):
        split_csv_file(args)
    return args


def process_git_repo(test_config, args):
    from control_tower.git_clone import clone_repo, post_artifact
    git_setting = test_config["git"]
    clone_repo(git_setting)
    post_artifact(GALLOPER_URL, TOKEN, PROJECT_ID, f"{BUILD_ID}.zip")
    setattr(args, "artifact", f"{BUILD_ID}.zip")
    setattr(args, "bucket", "tests")
    globals()["compile_and_run"] = "true"


def split_csv_file(args):
    from control_tower.csv_splitter import process_csv
    globals()["csv_array"] = process_csv(GALLOPER_URL, TOKEN, PROJECT_ID, args.artifact, args.bucket, CSV_PATH,
                                         args.concurrency[0])
    concurrency, execution_params, job_type, container = [], [], [], []
    for i in range(args.concurrency[0]):
        concurrency.append(1)
        execution_params.append(args.execution_params[0])
        job_type.append(args.job_type[0])
        container.append(args.container[0])
    args.concurrency = concurrency
    args.execution_params = execution_params
    args.job_type = job_type
    args.container = container


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


def start_job(args=None):
    if not args:
        args = arg_parse()
    if GALLOPER_URL and PROJECT_ID and TOKEN:
        package = get_project_package()
        allowable_load_generators = PROJECT_PACKAGE_MAPPER.get(package)["load_generators"]
        for each in args.concurrency:
            if allowable_load_generators != -1 and allowable_load_generators < each:
                print(f"Only {allowable_load_generators} parallel load generators allowable for {package} package.")
                exit(0)
    results_bucket = str(args.job_name).replace("_", "").replace(" ", "").lower()
    integration = []
    for each in ["jira", "report_portal", "email", "azure_devops"]:
        if getattr(args, each):
            integration.append(each)
    post_processor_args = {
        "galloper_url": GALLOPER_URL,
        "project_id": PROJECT_ID,
        "galloper_web_hook": GALLOPER_WEB_HOOK,
        "bucket": results_bucket,
        "prefix": DISTRIBUTED_MODE_PREFIX,
        "junit": args.junit,
        "token": TOKEN,
        "integration": integration,
        "email_recipients": args.email_recipients
    }
    arbiter = Arbiter(host=RABBIT_HOST, port=RABBIT_PORT, user=RABBIT_USER, password=RABBIT_PASSWORD)
    tasks = []
    for i in range(len(args.concurrency)):
        exec_params = deepcopy(args.execution_params[i])
        if mounts:
            exec_params['mounts'] = mounts
        if args.job_type[i] in ['perfgun', 'perfmeter']:
            exec_params['config_yaml'] = {}
            if LOKI_HOST:
                exec_params['loki_host'] = LOKI_HOST
                exec_params['loki_port'] = LOKI_PORT
            if ADDITIONAL_FILES:
                exec_params['additional_files'] = ADDITIONAL_FILES
            if globals().get("csv_array"):
                if 'additional_files' in exec_params:
                    exec_params['additional_files'] = {**exec_params['additional_files'],
                                                       **globals().get("csv_array")[i]}
                else:
                    exec_params['additional_files'] = globals().get("csv_array")[i]

            if 'additional_files' in exec_params:
                exec_params['additional_files'] = dumps(exec_params['additional_files']).replace("'", "\"")
            if JVM_ARGS:
                exec_params['JVM_ARGS'] = JVM_ARGS
            exec_params['build_id'] = BUILD_ID
            exec_params['DISTRIBUTED_MODE_PREFIX'] = DISTRIBUTED_MODE_PREFIX
            exec_params['galloper_url'] = GALLOPER_URL
            exec_params['bucket'] = BUCKET if not args.bucket else args.bucket
            exec_params['artifact'] = TEST if not args.artifact else args.artifact
            exec_params['results_bucket'] = results_bucket
            exec_params['save_reports'] = args.save_reports
            if globals().get("compile_and_run") == "true":
                exec_params["compile_and_run"] = "true"
            if PROJECT_ID:
                exec_params['project_id'] = PROJECT_ID
            if TOKEN:
                exec_params['token'] = TOKEN

        elif args.job_type[i] == "observer":
            execution_params = args.execution_params[i]

            exec_params["GALLOPER_URL"] = GALLOPER_URL
            exec_params["REPORTS_BUCKET"] = BUCKET
            exec_params["RESULTS_BUCKET"] = results_bucket
            exec_params["RESULTS_REPORT_NAME"] = DISTRIBUTED_MODE_PREFIX
            exec_params["GALLOPER_PROJECT_ID"] = PROJECT_ID
            exec_params["JOB_NAME"] = args.job_name
            exec_params['ARTIFACT'] = args.artifact
            exec_params['TESTS_BUCKET'] = args.bucket
            exec_params['REPORT_ID'] = BUILD_ID.replace("build_", "")

            if TOKEN:
                exec_params['token'] = TOKEN
            if mounts:
                exec_params['mounts'] = mounts if not execution_params["mounts"] else execution_params[
                    "mounts"]

        elif args.job_type[i] == "sast":
            if "code_path" in exec_params:
                print("Uploading code artifact to Galloper ...")
                with tempfile.TemporaryFile() as src_file:
                    with zipfile.ZipFile(src_file, "w", zipfile.ZIP_DEFLATED) as zip_file:
                        src_dir = os.path.abspath("/code")
                        for dirpath, _, filenames in os.walk(src_dir):
                            if dirpath == src_dir:
                                rel_dir = ""
                            else:
                                rel_dir = os.path.relpath(dirpath, src_dir)
                                zip_file.write(dirpath, arcname=rel_dir)
                            for filename in filenames:
                                zip_file.write(
                                    os.path.join(dirpath, filename),
                                    arcname=os.path.join(rel_dir, filename)
                                )
                    src_file.seek(0)
                    headers = {
                        "Authorization": f"Bearer {TOKEN}"
                    }
                    url = f"{GALLOPER_URL}/api/v1/artifacts/{PROJECT_ID}/sast/{args.test_id}.zip"
                    requests.post(
                        url, headers=headers, files={
                            "file": (f"{args.test_id}.zip", src_file)
                        }
                    )
        for _ in range(int(args.concurrency[i])):
            task_kwargs = {'job_type': str(args.job_type[i]), 'container': args.container[i],
                           'execution_params': exec_params, 'job_name': args.job_name}
            queue_name = args.channel[i] if len(args.channel) > i else "default"
            tasks.append(Task("execute", queue=queue_name, task_kwargs=task_kwargs))

    if args.job_type[0] in ['perfgun', 'perfmeter']:
        test_details = backend_perf_test_start_notify(args)
        group_id = arbiter.squad(tasks, callback=Task("post_process", task_kwargs=post_processor_args))
    elif args.job_type[0] == "observer":
        test_details = frontend_perf_test_start_notify(args)
        group_id = arbiter.squad(tasks)
    else:
        group_id = arbiter.squad(tasks)
        test_details = {}

    return arbiter, group_id, test_details


def frontend_perf_test_start_notify(args):
    if GALLOPER_URL:
        exec_params = args.execution_params[0]["cmd"] + " "
        browser = re.findall('-b (.+?) ', exec_params)
        browser_name = browser[0].split("_")[0].lower()
        browser_version = browser[0].split("_")[1]
        loops = re.findall('-l (.+?) ', exec_params)[0]
        aggregation = re.findall('-a (.+?) ', exec_params)[0]

        data = {
            "report_id": BUILD_ID.replace("build_", ""),
            "status": "In progress",
            "test_name": args.job_name,
            "base_url": "",
            "browser_name": browser_name,
            "browser_version": browser_version,
            "env": args.execution_params[0]["ENV"],
            "loops": loops,
            "aggregation": aggregation,
            "time": datetime.utcnow().isoformat(" ").split(".")[0]
        }
        headers = {'content-type': 'application/json'}
        if TOKEN:
            headers['Authorization'] = f'bearer {TOKEN}'

        response = requests.post(f"{GALLOPER_URL}/api/v1/observer/{PROJECT_ID}", json=data, headers=headers)
        return response.json()


def backend_perf_test_start_notify(args):
    if GALLOPER_URL:
        users_count = 0
        duration = 0
        vusers_var_names = ["vusers", "users", "users_count", "ramp_users", "user_count"]
        lg_type = JOB_TYPE_MAPPING.get(args.job_type[0], "other")
        tests_count = len(args.execution_params) if args.execution_params else 1
        if lg_type == 'jmeter':
            for i in range(tests_count):
                exec_params = args.execution_params[i]['cmd'] + " "
                test_type = re.findall('-Jtest.type=(.+?) ', exec_params)
                test_type = test_type[0] if len(test_type) else 'demo'
                environment = re.findall("-Jenv.type=(.+?) ", exec_params)
                environment = environment[0] if len(environment) else 'demo'
                test_name = re.findall("-Jtest_name=(.+?) ", exec_params)
                test_name = test_name[0] if len(test_name) else 'test'
                duration = re.findall("-JDURATION=(.+?) ", exec_params)
                duration = float(duration[0]) if len(duration) else 0
                for each in vusers_var_names:
                    if f'-j{each}' in exec_params.lower():
                        pattern = f'-j{each}=(.+?) '
                        vusers = re.findall(pattern, exec_params.lower())
                        users_count += int(vusers[0]) * args.concurrency[i]
                        break
        elif lg_type == 'gatling':
            for i in range(tests_count):
                exec_params = args.execution_params[i]
                test_type = exec_params['test_type'] if exec_params.get('test_type') else 'demo'
                test_name = exec_params['test'].split(".")[1].lower() if exec_params.get('test') else 'test'
                environment = exec_params['env'] if exec_params.get('env') else 'demo'
                if exec_params.get('GATLING_TEST_PARAMS'):
                    if '-dduration' in exec_params['GATLING_TEST_PARAMS'].lower():
                        duration = re.findall("-dduration=(.+?) ", exec_params['GATLING_TEST_PARAMS'].lower())[0]
                    for each in vusers_var_names:
                        if f'-d{each}' in exec_params['GATLING_TEST_PARAMS'].lower():
                            pattern = f'-d{each}=(.+?) '
                            vusers = re.findall(pattern, exec_params['GATLING_TEST_PARAMS'].lower())
                            users_count += int(vusers[0]) * args.concurrency[i]
                            break
        else:
            return {}
        start_time = datetime.utcnow().isoformat("T") + "Z"
        if args.test_id:
            test_id = args.test_id
        else:
            test_id = ""
        data = {'test_id': test_id, 'build_id': BUILD_ID, 'test_name': test_name, 'lg_type': lg_type, 'type': test_type,
                'duration': duration, 'vusers': users_count, 'environment': environment, 'start_time': start_time,
                'missed': 0, 'status': 'In progress'}
        if release_id:
            data['release_id'] = release_id

        headers = {'content-type': 'application/json'}
        if TOKEN:
            headers['Authorization'] = f'bearer {TOKEN}'
        if PROJECT_ID:
            url = f'{GALLOPER_URL}/api/v1/reports/{PROJECT_ID}'
        else:
            url = f'{GALLOPER_URL}/api/report'

        response = requests.post(url, json=data, headers=headers)

        try:
            print(response.json()["message"])
        except:
            print(response.text)

        if response.status_code == requests.codes.forbidden:
            print(response.json().get('Forbidden'))
            exit(126)
        return response.json()
    return {}


def get_project_package():
    try:
        url = f"{GALLOPER_URL}/api/v1/project/{PROJECT_ID}"
        headers = {'content-type': 'application/json', 'Authorization': f'bearer {TOKEN}'}
        package = requests.get(url, headers=headers).json()["package"]
    except:
        package = "custom"
    return package


def start_job_exec(args=None):
    start_job(args)
    exit(0)


def check_ready(result):
    if result and not result.ready():
        return False
    return True


def check_test_is_saturating(test_id=None, deviation=0.02, max_deviation=0.05):
    if test_id and PROJECT_ID and SAMPLER and REQUEST:
        url = f'{GALLOPER_URL}/api/v1/saturation'
        headers = {'Authorization': f'bearer {TOKEN}'} if TOKEN else {}
        headers["Content-type"] = "application/json"
        params = {
            "test_id": test_id,
            "project_id": PROJECT_ID,
            "sampler": SAMPLER,
            "request": REQUEST,
            "wait_till": CALCULATION_DELAY,
            "max_errors": MAX_ERRORS,
            "deviation": deviation,
            "max_deviation": max_deviation,
            "u_aggr": U_AGGR
        }
        return requests.get(url, params=params, headers=headers).json()
    return {"message": "Test is in progress", "code": 0}


def track_job(arbiter, group_id, test_id=None, deviation=0.02, max_deviation=0.05):
    result = 0
    test_start = time()
    max_duration = -1
    if GALLOPER_URL and PROJECT_ID and TOKEN:
        package = get_project_package()
        max_duration = PROJECT_PACKAGE_MAPPER.get(package)["duration"]

    while not arbiter.status(group_id)['state'] == 'done':
        sleep(60)
        if CHECK_SATURATION:
            test_status = check_test_is_saturating(test_id, deviation, max_deviation)
            print("Status:")
            print(test_status)
            if test_status.get("code", 0) == 1:
                print("Kill job")
                arbiter.kill_group(group_id)
                print("Terminated")
                result = 1
        else:
            print("Still processing ...")
        if test_was_canceled(test_id) and result != 1:
            print("Test was canceled")
            arbiter.kill_group(group_id)
            print("Terminated")
            result = 1
        if max_duration != -1 and max_duration <= int((time() - test_start)) and result != 1:
            print(f"Exceeded max test duration - {max_duration} sec")
            arbiter.kill_group(group_id)
    arbiter.close()
    return result


def test_was_canceled(test_id):
    try:
        if test_id and PROJECT_ID and GALLOPER_URL and report_type:
            url = f'{GALLOPER_URL}/api/v1/reports/{PROJECT_ID}/{REPORT_TYPE_MAPPING.get(report_type)}/{test_id}/status'
            headers = {'Authorization': f'bearer {TOKEN}'} if TOKEN else {}
            headers["Content-type"] = "application/json"
            status = requests.get(url, headers=headers).json()['message']
            return True if status in ["Canceled", "Finished"] else False
        return False
    except:
        return False


def _start_and_track(args=None):
    if not args:
        args = arg_parse()
    deviation = DEVIATION if args.deviation == 0 else args.deviation
    max_deviation = MAX_DEVIATION if args.max_deviation == 0 else args.max_deviation
    arbiter, group_id, test_details = start_job(args)
    print("Job started, waiting for containers to settle ... ")
    track_job(arbiter, group_id, test_details.get("id", None), deviation, max_deviation)
    if args.junit:
        print("Processing junit report ...")
        process_junit_report(args)
    if args.job_type[0] in ["dast", "sast"] and args.quality_gate:
        print("Processing security quality gate ...")
        process_security_quality_gate(args)
    if args.artifact == f"{BUILD_ID}.zip":
        from control_tower.git_clone import delete_artifact
        delete_artifact(GALLOPER_URL, TOKEN, PROJECT_ID, args.artifact)
    if globals().get("csv_array"):
        from control_tower.csv_splitter import delete_csv
        for each in globals().get("csv_array"):
            csv_name = list(each.keys())[0].replace("tests/", "")
            delete_csv(GALLOPER_URL, TOKEN, PROJECT_ID, csv_name)


def start_and_track(args=None):
    _start_and_track(args)
    exit(0)


def process_security_quality_gate(args):
    # Save jUnit report as file to local filesystem
    junit_report_data = download_junit_report(
        args.job_type[0], f"{args.test_id}_junit_report.xml", retry=12
    )
    if junit_report_data:
        with open(os.path.join(args.report_path, f"junit_report_{args.test_id}.xml"), "w") as rept:
            rept.write(junit_report_data.text)
    # Quality Gate
    quality_gate_data = download_junit_report(
        args.job_type[0], f"{args.test_id}_quality_gate_report.json", retry=12
    )
    if not quality_gate_data:
        print("No security quality gate data found")
        return
    quality_gate = loads(quality_gate_data.text)
    if quality_gate["quality_gate_stats"]:
        for line in quality_gate["quality_gate_stats"]:
            print(line)
    if quality_gate["fail_quality_gate"]:
        exit(1)


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
    headers = {'Authorization': f'bearer {TOKEN}'} if TOKEN else {}
    junit_report = requests.get(url, headers=headers, allow_redirects=True)
    if junit_report.status_code != 200 or 'botocore.errorfactory.NoSuchKey' in junit_report.text:
        print("Waiting for report to be accessible ...")
        retry -= 1
        if retry == 0:
            return None
        sleep(10)
        return download_junit_report(results_bucket, file_name, retry)
    return junit_report


# if __name__ == "__main__":
#     from control_tower.config_mock import BulkConfig
#     args = BulkConfig(
#         bulk_container=["getcarrier/perfmeter:latest"],
#         bulk_params=[{"cmd": "-n -t /mnt/jmeter/FloodIO.jmx -Jtest.type=debug -Jenv.type=debug "
#                              "-Jinflux.host= -JVUSERS=100 -JDURATION=1200 "
#                              "-JRAMP_UP=60 -Jtest_name=Flood"}],
#         job_type=["perfmeter"],
#         job_name='DemoTest',
#         bulk_concurrency=[2]
#     )
#     groups, test_details, post_processor_args = start_job(args)
#     for group in groups:
#         track_job(group, test_details["id"])
