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

import os
SSL_CERTS = os.environ.get('SSL_CERTS', '')

from control_tower import ssl_support
ssl_support.init(SSL_CERTS)

import argparse
import logging
import re
import tempfile
import zipfile
from copy import deepcopy
from datetime import datetime
from json import dumps
from time import sleep, time
import xml.etree.ElementTree as et
from traceback import format_exc

import ssl
import arbiter
import requests
from centry_loki import log_loki

from control_tower.constants import *
from control_tower.utils import build_api_url

if REPORT_ID:
    loki_context = {
        "url": f"{GALLOPER_URL.replace('https://', 'http://')}:{LOKI_PORT}/loki/api/v1/push",
        "hostname": "control-tower",
        "labels": {
            "build_id": BUILD_ID,
            "project": PROJECT_ID,
            "report_id": REPORT_ID
        }
    }
    logger = log_loki.get_logger(loki_context)
else:
    logger = logging.getLogger()


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
    parser.add_argument('-int', '--integrations', default={}, type=str)
    args, _ = parser.parse_known_args()
    if args.test_id and GALLOPER_URL:
        args = append_test_config(args)
    return args


def append_test_config(args):
    headers = {'content-type': 'application/json'}
    if TOKEN:
        headers['Authorization'] = f'bearer {TOKEN}'
    url = f"{GALLOPER_URL}/api/v1/shared/job_type/{PROJECT_ID}/{args.test_id}"
    # get job_type
    test_config = requests.get(url, headers=headers)
    try:
        test_config = test_config.json()
    except Exception as exc:
        logger.info(test_config.text)
        raise exc
    job_type = args.job_type[0] if args.job_type else test_config["job_type"]
    lg_type = JOB_TYPE_MAPPING.get(job_type, "other")
    params = {}
    execution_params = []
    concurrency = []
    container = []
    job_type = []
    tests_count = len(args.concurrency) if args.concurrency else 1
    # prepare params
    for i in range(tests_count):
        if lg_type == 'jmeter':
            url = f"{GALLOPER_URL}/api/v1/backend_performance/test/{PROJECT_ID}/{args.test_id}"
            if args.execution_params and "cmd" in args.execution_params[i].keys():
                exec_params = args.execution_params[i]['cmd'].split("-J")
                for each in exec_params:
                    if "=" in each:
                        _ = each.split("=")
                        params[_[0]] = str(_[1]).strip()
        elif lg_type == 'gatling':
            url = f"{GALLOPER_URL}/api/v1/backend_performance/test/{PROJECT_ID}/{args.test_id}"
            if args.execution_params and "GATLING_TEST_PARAMS" in args.execution_params[i]:
                exec_params = args.execution_params[i]['GATLING_TEST_PARAMS'].split("-D")
                for each in exec_params:
                    if "=" in each:
                        _ = each.split("=")
                        params[_[0]] = str(_[1]).strip()
        elif lg_type == 'dast':
            url = f"{GALLOPER_URL}/api/v1/security/test/{PROJECT_ID}/{args.test_id}"
        elif lg_type == 'observer':
            url = f"{GALLOPER_URL}/api/v1/ui_performance/test/{PROJECT_ID}/{args.test_id}"
            params = {}
        else:
            logger.info(f"No data found for test_id={args.test_id}")
            raise RuntimeError(f"No data found for test_id={args.test_id}")

        data = {
            "params": params,
            "type": "config"
        }
        # merge params with test config
        test_config = requests.post(url, json=data, headers=headers)
        try:
            test_config = test_config.json()
        except Exception as exc:
            logger.info(test_config.text)
            raise exc
        # set args and env vars
        try:
            execution_params.append(loads(test_config["execution_params"]))
            concurrency.append(test_config["concurrency"])
            container.append(test_config["container"])
            job_type.append(test_config["job_type"])
        except Exception as e:
            print(e)
        setattr(args, "job_name", test_config["job_name"])
        for each in ["job_name", "email_recipients"]:
            if not getattr(args, each) and each in test_config.keys():
                setattr(args, each, test_config[each])
        for each in ["container", "job_type", "channel"]:
            if not getattr(args, each) and each in test_config.keys():
                setattr(args, each, [test_config[each]])
        for each in ["junit", "quality_gate", "save_reports", "jira",
                     "report_portal", "email", "azure_devops"]:
            if not getattr(args, each) and each in test_config.keys():
                setattr(args, each, str2bool(test_config[each]))
        if "integrations" in test_config.keys():
            setattr(args, "integrations", test_config["integrations"])
        env_vars = test_config["cc_env_vars"]
        for key, value in env_vars.items():
            environ[key] = value


    setattr(args, "execution_params", execution_params)
    setattr(args, "concurrency", concurrency)
    setattr(args, "container", container)
    setattr(args, "job_type", job_type)
    s3_settings = args.integrations.get("system", {}).get("s3_integration", {})
    environ["report_type"] = JOB_TYPE_MAPPING.get(args.job_type[0], "other")
    if "git" in test_config.keys():
        process_git_repo(test_config, args, s3_settings)
    elif "local_path" in test_config.keys():
        process_local_mount(test_config, args, s3_settings)
    elif 'artifact' in test_config:
        setattr(args, 'artifact', test_config['artifact']['file_name'])
        setattr(args, 'bucket', test_config['artifact'].get('bucket', 'tests'))
    if CSV_FILES:
        split_csv_file(args, s3_settings)
    print(args)
    return args


def process_git_repo(test_config, args, s3_settings):
    from control_tower.git_clone import clone_repo, post_artifact
    git_setting = test_config["git"]
    clone_repo(git_setting)
    post_artifact(GALLOPER_URL, TOKEN, PROJECT_ID, f"{BUILD_ID}.zip", s3_settings)
    setattr(args, "artifact", f"{BUILD_ID}.zip")
    setattr(args, "bucket", "tests")
    globals()["compile_and_run"] = "true"


def process_local_mount(test_config, args, s3_settings):
    from control_tower.git_clone import post_artifact
    local_path = test_config["local_path"]
    post_artifact(GALLOPER_URL, TOKEN, PROJECT_ID, f"{BUILD_ID}.zip", s3_settings, local_path)
    setattr(args, "artifact", f"{BUILD_ID}.zip")
    setattr(args, "bucket", "tests")
    globals()["compile_and_run"] = "true"


def split_csv_file(args, s3_settings):
    from control_tower.csv_splitter import process_csv
    globals()["csv_array"] = process_csv(GALLOPER_URL, TOKEN, PROJECT_ID, args.artifact,
                                         args.bucket, CSV_FILES,
                                         args.concurrency[0], s3_settings)
    concurrency, execution_params, job_type, container, channel = [], [], [], [], []
    for i in range(args.concurrency[0]):
        concurrency.append(1)
        execution_params.append(args.execution_params[0])
        job_type.append(args.job_type[0])
        container.append(args.container[0])
        channel.append(args.channel[0])
    args.concurrency = concurrency
    args.execution_params = execution_params
    args.job_type = job_type
    args.container = container
    args.channel = channel


# def parse_id():
#     parser = argparse.ArgumentParser(description='Carrier Command Center')
#     parser.add_argument('-g', '--groupid', type=str, default="",
#                         help="ID of the group for a task")
#     parser.add_argument('-c', '--container', type=str,
#                         help="Name of container to run the job e.g. getcarrier/dusty:latest")
#     parser.add_argument('-t', '--job_type', type=str,
#                         help="Type of a job: e.g. sast, dast, perf-jmeter, perf-ui")
#     parser.add_argument('-n', '--job_name', type=str,
#                         help="Name of a job (e.g. unique job ID, like %JOBNAME%_%JOBID%)")
#     args, _ = parser.parse_known_args()
#     if args.groupid:
#         for unparsed in _:
#             args.groupid += unparsed
#     if 'group_id' in args.groupid:
#         args.groupid = loads(args.groupid)
#     return args


def start_job(args=None):
    if not args:
        args = arg_parse()
    if GALLOPER_URL and PROJECT_ID and TOKEN:
        package = get_project_package()
        allowable_load_generators = PROJECT_PACKAGE_MAPPER.get(package)["load_generators"]
        for each in args.concurrency:
            if allowable_load_generators != -1 and allowable_load_generators < each:
                raise Exception(
                    f"Only {allowable_load_generators} parallel load generators allowable for {package} package.")
    finalizer_task = None

    # Cloud integrations
    aws_settings = args.integrations.get("clouds", {}).get("aws_integration", None)
    gcp_settings = args.integrations.get("clouds", {}).get("gcp_integration", None)
    kubernetes_settings = args.integrations.get("clouds", {}).get("kubernetes", None)
    s3_settings = args.integrations.get("system", {}).get("s3_integration", {})

    try:
        if aws_settings:
            from control_tower.cloud import create_aws_instances
            update_test_status(status="Preparing...", percentage=5,
                               description="Request AWS spot instances")
            finalizer_task = create_aws_instances(args, aws_settings)
        elif gcp_settings:
            from control_tower.cloud import create_gcp_instances
            update_test_status(status="Preparing...", percentage=5,
                               description="Request GCP Compute instances")
            finalizer_task = create_gcp_instances(args, gcp_settings)
    except Exception as e:
        logger.error(e)
        raise e

    results_bucket = str(args.job_name).replace("_", "").replace(" ", "").lower()
    # arb = arbiter.Arbiter(host=RABBIT_HOST, port=RABBIT_PORT, user=RABBIT_USER,
    #                       password=RABBIT_PASSWORD, vhost=RABBIT_VHOST, timeout=120,
    #                       use_ssl=RABBIT_USE_SSL, ssl_verify=RABBIT_SSL_VERIFY)
    #
    event_node_runtime = environ.get("ARBITER_RUNTIME", "rabbitmq")
    #
    if event_node_runtime == "rabbitmq":
        node_config = {
            "use_ssl": environ.get("RABBIT_USE_SSL", "").lower() in ["true", "yes"],
            "ssl_verify": environ.get("RABBIT_SSL_VERIFY", "").lower() in ["true", "yes"],
            "host": environ.get("RABBIT_HOST"),
            "port": int(environ.get("RABBIT_PORT", "5672")),
            "user": environ.get("RABBIT_USER"),
            "password": environ.get("RABBIT_PASSWORD"),
            "vhost": environ.get("RABBIT_VHOST"),
            "queue": "tasks",
            "hmac_key": None,
            "hmac_digest": "sha512",
            "callback_workers": int(environ.get("EVENT_NODE_WORKERS", "1")),
            "mute_first_failed_connections": 10,
        }
        #
        ssl_context=None
        ssl_server_hostname=None
        #
        if node_config.get("use_ssl", False):
            ssl_context = ssl.create_default_context()
            if node_config.get("ssl_verify", False) is True:
                ssl_context.verify_mode = ssl.CERT_REQUIRED
                ssl_context.check_hostname = True
                ssl_context.load_default_certs()
            else:
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
            ssl_server_hostname = node_config.get("host")
        #
        event_node = arbiter.EventNode(
            host=node_config.get("host"),
            port=node_config.get("port", 5672),
            user=node_config.get("user", ""),
            password=node_config.get("password", ""),
            vhost=node_config.get("vhost", "carrier"),
            event_queue=node_config.get("queue", "rpc"),
            hmac_key=node_config.get("hmac_key", None),
            hmac_digest=node_config.get("hmac_digest", "sha512"),
            callback_workers=node_config.get("callback_workers", 1),
            ssl_context=ssl_context,
            ssl_server_hostname=ssl_server_hostname,
            mute_first_failed_connections=node_config.get("mute_first_failed_connections", 10),  # pylint: disable=C0301
        )
    elif event_node_runtime == "redis":
        node_config = {
            "host": environ.get("REDIS_HOST"),
            "port": int(environ.get("REDIS_PORT", "6379")),
            "password": environ.get("REDIS_PASSWORD"),
            "queue": environ.get("REDIS_VHOST"),
            "hmac_key": None,
            "hmac_digest": "sha512",
            "callback_workers": int(environ.get("EVENT_NODE_WORKERS", "1")),
            "mute_first_failed_connections": 10,
            "use_ssl": environ.get("REDIS_USE_SSL", "").lower() in ["true", "yes"],
        }
        #
        event_node = arbiter.RedisEventNode(
            host=node_config.get("host"),
            port=node_config.get("port", 6379),
            password=node_config.get("password", ""),
            event_queue=node_config.get("queue", "events"),
            hmac_key=node_config.get("hmac_key", None),
            hmac_digest=node_config.get("hmac_digest", "sha512"),
            callback_workers=node_config.get("callback_workers", 1),
            mute_first_failed_connections=node_config.get("mute_first_failed_connections", 10),  # pylint: disable=C0301
            use_ssl=node_config.get("use_ssl", False),
        )
    else:
        raise ValueError(f"Unsupported arbiter runtime: {event_node_runtime}")
    #
    arb = arbiter.Arbiter(event_node=event_node)
    tasks = []
    exec_params = {}
    for i in range(len(args.concurrency)):
        exec_params = deepcopy(args.execution_params[i])
        if mounts:
            exec_params['mounts'] = mounts
        if args.job_type[i] in {'perfgun', 'perfmeter'}:
            exec_params['integrations'] = dumps(args.integrations)
            exec_params['config_yaml'] = {}
            if LOKI_HOST:
                exec_params['loki_host'] = LOKI_HOST
                exec_params['loki_port'] = LOKI_PORT
            if ADDITIONAL_FILES:
                exec_params['additional_files'] = ADDITIONAL_FILES
            if globals().get("csv_array"):
                for _file in globals().get("csv_array")[i]:
                    if 'additional_files' in exec_params:
                        exec_params['additional_files'] = {**exec_params['additional_files'],
                                                           **_file}
                    else:
                        exec_params['additional_files'] = _file

            if 'additional_files' in exec_params:
                exec_params['additional_files'] = dumps(
                    exec_params['additional_files']).replace("'", "\"")
            if JVM_ARGS:
                exec_params['JVM_ARGS'] = JVM_ARGS
            exec_params['build_id'] = BUILD_ID
            exec_params["test_name"] = args.job_name
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
            if not REPORT_ID:
                test_details = backend_perf_test_start_notify(args)
                globals()["REPORT_ID"] = str(test_details["id"]) \
                    if "id" in test_details.keys() else None
            exec_params['report_id'] = REPORT_ID

        elif args.job_type[i] == "observer":
            execution_params = args.execution_params[i]

            exec_params["GALLOPER_URL"] = GALLOPER_URL
            exec_params['project_id'] = PROJECT_ID
            exec_params["REPORTS_BUCKET"] = BUCKET
            exec_params["RESULTS_BUCKET"] = results_bucket
            exec_params["RESULTS_REPORT_NAME"] = DISTRIBUTED_MODE_PREFIX
            exec_params["GALLOPER_PROJECT_ID"] = PROJECT_ID
            exec_params["JOB_NAME"] = args.job_name
            exec_params['ARTIFACT'] = args.artifact
            exec_params['TESTS_BUCKET'] = args.bucket
            exec_params['integrations'] = dumps(args.integrations)
            if REPORT_ID:
                exec_params['REPORT_ID'] = REPORT_ID
                exec_params['report_id'] = REPORT_ID
            else:
                exec_params['REPORT_ID'] = BUILD_ID.replace("build_", "")

            if TOKEN:
                exec_params['token'] = TOKEN
            if mounts:
                exec_params['mounts'] = mounts if not execution_params["mounts"] \
                    else execution_params["mounts"]

        elif args.job_type[i] in ("sast", "dependency"):
            exec_params['build_id'] = BUILD_ID
            exec_params['report_id'] = REPORT_ID
            exec_params['project_id'] = PROJECT_ID

            if "code_path" in exec_params:
                logger.info("Uploading code artifact to Galloper ...")
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
                    # upload artifact
                    url = f"{GALLOPER_URL}/api/v1/artifacts/artifacts/{PROJECT_ID}/sast/"
                    file_payload = {"file": (f"{BUILD_ID}.zip", src_file)}
                    requests.post(url, params=s3_settings, headers=headers, files=file_payload)

        if kubernetes_settings:
            task_kwargs = {
                'job_type': str(args.job_type[i]),
                'container': args.container[i],
                'execution_params': exec_params,
                'job_name': args.job_name,
                'kubernetes_settings': {
                    "jobs_count": int(args.concurrency[i]),
                    "host": kubernetes_settings["hostname"],
                    "token": kubernetes_settings["k8s_token"],
                    "namespace": kubernetes_settings["namespace"],
                    "secure_connection": kubernetes_settings["secure_connection"],
                    "scaling_cluster": kubernetes_settings["scaling_cluster"]
                }
            }
            queue_name = args.channel[i] if len(args.channel) > i else "__internal"
            tasks.append(
                arbiter.Task("execute_kuber", queue=queue_name, task_kwargs=task_kwargs))
        else:
            queue_name = args.channel[i] if len(args.channel) > i else "default"
            for _ in range(int(args.concurrency[i])):
                task_kwargs = {'job_type': str(args.job_type[i]),
                               'container': args.container[i],
                               'execution_params': exec_params, 'job_name': args.job_name}

                tasks.append(
                    arbiter.Task("execute", queue=queue_name, task_kwargs=task_kwargs))
    if args.job_type[0] in {'perfgun', 'perfmeter'}:
        post_processor_args = {
            "galloper_url": GALLOPER_URL,
            "project_id": PROJECT_ID,
            "galloper_web_hook": GALLOPER_WEB_HOOK,
            "report_id": REPORT_ID,
            "bucket": results_bucket,
            "build_id": BUILD_ID,
            "prefix": DISTRIBUTED_MODE_PREFIX,
            "token": TOKEN,
            "integration": dumps(args.integrations),
            "exec_params": dumps(exec_params),
        }
        queue_name = args.channel[0] if len(args.channel) > 0 else "default"
        tasks.append(
            arbiter.Task("post_process", queue=queue_name, task_kwargs=post_processor_args)
        )

    if finalizer_task:
        tasks.append(finalizer_task)

    try:
        group_id = arb.squad(tasks)
        # group_id = arb.squad(
        #     tasks, callback=arbiter.Task(
        #         "post_process",
        #         queue=args.channel[0],
        #         task_kwargs=post_processor_args
        #     )
        # )
    except (NameError, KeyError) as e:
        logger.error(e)
        raise e

    test_details = {}
    if REPORT_ID:
        update_test_status(status="Preparing...", percentage=5,
                        description="We have enough workers to run the test. The test will start soon")
        test_details = {"id": REPORT_ID}
    else:
        if args.job_type[0] == "observer":
            test_details = frontend_perf_test_start_notify(args)

    return arb, group_id, test_details


def update_test_status(status, percentage, description):
    module = CENTRY_MODULES_MAPPING.get(environ.get("report_type"))
    data = {"test_status": {"status": status, "percentage": percentage,
                            "description": description}}
    headers = {'content-type': 'application/json', 'Authorization': f'bearer {TOKEN}'}
    url = f'{GALLOPER_URL}/api/v1/{module}/report_status/{PROJECT_ID}/{REPORT_ID}'
    response = requests.put(url, json=data, headers=headers)
    try:
        logger.info(response.json()["message"])
    except:
        logger.info(response.text)


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
            "test_uid": args.test_id,
            "status": "In progress",
            "test_name": args.job_name,
            "base_url": "",
            "browser_name": browser_name,
            "browser_version": browser_version,
            "loops": loops,
            "aggregation": aggregation,
            "time": datetime.utcnow().isoformat(" ").split(".")[0]
        }
        headers = {'content-type': 'application/json'}
        if TOKEN:
            headers['Authorization'] = f'bearer {TOKEN}'

        response = requests.post(f"{GALLOPER_URL}/api/v1/ui_performance/reports/{PROJECT_ID}", json=data,
                                 headers=headers)
        try:
            logger.info(response.json()["message"])
        except:
            logger.info(response.text)
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
                test_type = re.findall('-Jtest_type=(.+?) ', exec_params)
                test_type = test_type[0] if len(test_type) else 'demo'
                environment = re.findall("-Jenv_type=(.+?) ", exec_params)
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
                test_type = exec_params['test_type'] if exec_params.get(
                    'test_type') else 'demo'
                test_name = exec_params['test'].split(".")[1].lower() if exec_params.get(
                    'test') else 'test'
                environment = exec_params['env'] if exec_params.get('env') else 'demo'
                if exec_params.get('GATLING_TEST_PARAMS'):
                    if '-dduration' in exec_params['GATLING_TEST_PARAMS'].lower():
                        duration = re.findall("-dduration=(.+?) ",
                                              exec_params['GATLING_TEST_PARAMS'].lower())[0]
                    for each in vusers_var_names:
                        if f'-d{each}' in exec_params['GATLING_TEST_PARAMS'].lower():
                            pattern = f'-d{each}=(.+?) '
                            vusers = re.findall(pattern,
                                                exec_params['GATLING_TEST_PARAMS'].lower())
                            users_count += int(vusers[0]) * args.concurrency[i]
                            break
        else:
            return {}
        start_time = datetime.utcnow().isoformat("T") + "Z"
        if args.test_id:
            test_id = args.test_id
        else:
            test_id = ""
        data = {'test_id': test_id, 'build_id': BUILD_ID, 'test_name': test_name,
                'lg_type': lg_type, 'type': test_type,
                'duration': duration, 'vusers': users_count, 'environment': environment,
                'start_time': start_time,
                'missed': 0, "test_params": args.execution_params[0]['cmd']}

        headers = {'content-type': 'application/json'}
        if TOKEN:
            headers['Authorization'] = f'bearer {TOKEN}'
        url = f'{GALLOPER_URL}/api/v1/backend_performance/reports/{PROJECT_ID}'

        response = requests.post(url, json=data, headers=headers)
        res = {}
        try:
            res = response.json()
            _loki_context = {
                "url": f"{GALLOPER_URL.replace('https://', 'http://')}:{LOKI_PORT}/loki/api/v1/push",
                "hostname": "control-tower", "labels": {"build_id": BUILD_ID,
                                                        "project": PROJECT_ID,
                                                        "report_id": str(res.get("id"))}}
            globals()["logger"] = log_loki.get_logger(_loki_context)
        except:
            logger.error(response.text)

        if response.status_code == requests.codes.forbidden:
            logger.error(response.json().get('Forbidden'))
            raise Exception(response.json().get('Forbidden'))
        return res
    return {}


def get_project_package():
    try:
        url = f"{GALLOPER_URL}/api/v1/projects/project/{PROJECT_ID}"
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


def test_finished(report_id=REPORT_ID):
    module = CENTRY_MODULES_MAPPING.get(environ.get("report_type"))
    headers = {'Authorization': f'bearer {TOKEN}'} if TOKEN else {}
    headers["Content-type"] = "application/json"
    url = f'{GALLOPER_URL}/api/v1/{module}/report_status/{PROJECT_ID}/{report_id}'
    res = requests.get(url, headers=headers).json()
    return res["message"].lower() in {
        "finished", "failed", "success",
        'canceled', 'cancelled', 'post processing (manual)',
        'error'
    }


def send_minio_dump_flag(result_code: int) -> None:
    # do we need to check report_type?
    api_url = build_api_url(CENTRY_MODULES_MAPPING.get(environ.get("report_type")), 'reports', skip_mode=True, trailing_slash=True)
    url = f'{GALLOPER_URL}{api_url}{PROJECT_ID}'
    logger.info("Saving logs to minio %s", api_url)
    headers = {'Content-type': 'application/json'}
    if TOKEN:
        headers['Authorization'] = f'bearer {TOKEN}'
    requests.patch(url, headers=headers, json={'build_id': BUILD_ID, 'result_code': result_code})


def track_job(bitter, group_id, test_id=None, deviation=0.02, max_deviation=0.05):
    result = 0
    test_start = time()
    max_duration = -1
    if GALLOPER_URL and PROJECT_ID and TOKEN:
        package = get_project_package()
        max_duration = PROJECT_PACKAGE_MAPPER.get(package)["duration"]

    while not test_finished(test_id):
        sleep(60)
        if CHECK_SATURATION:
            test_status = check_test_is_saturating(test_id, deviation, max_deviation)
            if test_status.get("code", 0) == 1:
                logger.info("Kill job")
                try:
                    bitter.kill_group(group_id)
                except Exception as e:
                    logger.info(e)
                logger.info("Terminated")
                result = 1
        else:
            logger.info("Still processing ...")
        if test_was_canceled(test_id) and result != 1:
            logger.info("Test was cancelled")
            try:
                bitter.kill_group(group_id)
            except Exception as e:
                logger.info(e)
            finally:
                logger.info("Terminated")
                result = 1
                break
        if max_duration != -1 and max_duration <= int((time() - test_start)) and result != 1:
            logger.info(f"Exceeded max test duration - {max_duration} sec")
            try:
                bitter.kill_group(group_id)
            except Exception as e:
                logger.info(e)
    try:
        bitter.close()
    except Exception as e:
        # logger.info(e)
        ...
    return result


def test_was_canceled(test_id):
    try:
        if test_id and PROJECT_ID and GALLOPER_URL and environ.get("report_type"):
            module = CENTRY_MODULES_MAPPING.get(environ.get("report_type"))
            url = f'{GALLOPER_URL}/api/v1/{module}/report_status/{PROJECT_ID}/{test_id}'
            headers = {'Authorization': f'bearer {TOKEN}'} if TOKEN else {}
            headers["Content-type"] = "application/json"
            status = requests.get(url, headers=headers).json()['message']
            return status in {'Cancelled', "Canceled", "post processing (manual)"}
        return False
    except:
        return False


def _start_and_track(args=None):
    if not args:
        args = arg_parse()
    s3_settings = args.integrations.get("system", {}).get("s3_integration", {})
    deviation = DEVIATION if args.deviation == 0 else args.deviation
    max_deviation = MAX_DEVIATION if args.max_deviation == 0 else args.max_deviation
    bitter, group_id, test_details = start_job(args)
    logger.info("Job started, waiting for containers to settle ... ")
    track_job(bitter, group_id, test_details.get("id", None), deviation, max_deviation)
    if args.job_type[0] in {"dast", "sast", "dependency"} and args.quality_gate:
        logger.info("Processing security quality gate ...")
        process_security_quality_gate(args, s3_settings)
    if args.artifact == f"{BUILD_ID}.zip":
        from control_tower.git_clone import delete_artifact
        delete_artifact(GALLOPER_URL, TOKEN, PROJECT_ID, args.artifact, s3_settings)
    if globals().get("csv_array"):
        from control_tower.csv_splitter import delete_csv
        for each in globals().get("csv_array"):
            for _ in each:
                csv_name = list(_.keys())[0].replace("tests/", "")
                delete_csv(GALLOPER_URL, TOKEN, PROJECT_ID, csv_name)
    if args.integrations and "quality_gate" in args.integrations.get("processing", {}):
        if args.job_type[0] in {'perfgun', 'perfmeter'}:
            logger.info("Processing junit report ...")
            process_junit_report(args, s3_settings)


def start_and_track(args=None):
    status_code = 200
    try:
        _start_and_track(args)
    except:
        status_code = 500
        logger.error(format_exc())
        raise
    finally:
        send_minio_dump_flag(status_code)
    exit(0)


def process_security_quality_gate(args, s3_settings):
    # Save jUnit report as file to local filesystem
    junit_report_data = download_junit_report(
        s3_settings, args.job_type[0], f"{args.test_id}_junit_report.xml", retry=12
    )
    if junit_report_data:
        with open(os.path.join(args.report_path, f"junit_report_{args.test_id}.xml"),
                  "w") as rept:
            rept.write(junit_report_data.text)
    # Quality Gate
    quality_gate_data = download_junit_report(
        s3_settings, args.job_type[0], f"{args.test_id}_quality_gate_report.json", retry=12
    )
    if not quality_gate_data:
        logger.info("No security quality gate data found")
        return
    quality_gate = loads(quality_gate_data.text)
    if quality_gate["quality_gate_stats"]:
        for line in quality_gate["quality_gate_stats"]:
            logger.info(line)
    if quality_gate["fail_quality_gate"]:
        raise Exception


def process_junit_report(args, s3_settings):
    file_name = "junit_report_{}.xml".format(BUILD_ID)
    results_bucket = str(args.job_name).replace("_", "").lower()
    junit_report = download_junit_report(s3_settings, results_bucket, file_name, retry=12)
    if junit_report:
        with open("{}/{}".format(args.report_path, file_name), "w") as f:
            f.write(junit_report.text)
        testsuite = et.fromstring(junit_report.text).find("./testsuite[@name='Quality gate ']")
        if testsuite:
            failed = testsuite.get('failures')
            total = testsuite.get('tests')
            errors = testsuite.get('errors')
            skipped = testsuite.get('skipped')
            failures = [failure.get('message') for failure in testsuite.findall("./testcase/failure")]
            logger.info("**********************************************")
            logger.info("* Performance testing jUnit report | Carrier *")
            logger.info("**********************************************")
            logger.info(f"Tests run: {total}, Failures: {failed}, Errors: {errors}, Skipped: {skipped}")
            quality_gate_rate = int(args.integrations["processing"]["quality_gate"].get(
                "settings", {}).get("per_request_results", {}).get("percentage_of_failed_requests", 20))
            if failures:
                for failure in failures:
                    logger.error(failure)
                raise Exception('Quality gate status: FAILED.')
            else:
                logger.info(
                    f"Quality gate status: PASSED. Missed threshold rate lower than {quality_gate_rate}%")


def download_junit_report(s3_settings, results_bucket, file_name, retry):
    if PROJECT_ID:
        url = f'{GALLOPER_URL}/api/v1/artifacts/artifact/{PROJECT_ID}/{results_bucket}/{file_name}'
    else:
        url = f'{GALLOPER_URL}/artifacts/{results_bucket}/{file_name}'
    headers = {'Authorization': f'bearer {TOKEN}'} if TOKEN else {}
    junit_report = requests.get(url, params=s3_settings, headers=headers, allow_redirects=True)
    if junit_report.status_code != 200 or 'botocore.errorfactory.NoSuchKey' in junit_report.text:
        logger.info("Waiting for report to be accessible ...")
        retry -= 1
        if retry == 0:
            return None
        sleep(10)
        return download_junit_report(s3_settings, results_bucket, file_name, retry)
    return junit_report

# if __name__ == "__main__":
#     from control_tower.config_mock import BulkConfig
#     args = BulkConfig(
#         bulk_container=["getcarrier/perfmeter:latest"],
#         bulk_params=[{"cmd": "-n -t /mnt/jmeter/FloodIO.jmx -Jtest_type=debug -Jenv_type=debug "
#                              "-Jinflux.host= -JVUSERS=100 -JDURATION=1200 "
#                              "-JRAMP_UP=60 -Jtest_name=Flood"}],
#         job_type=["perfmeter"],
#         job_name='DemoTest',
#         bulk_concurrency=[2]
#     )
#     groups, test_details, post_processor_args = start_job(args)
#     for group in groups:
#         track_job(group, test_details["id"])
