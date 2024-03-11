#  Copyright (c) 2024 getcarrier.io
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

from json import dumps
from time import sleep, time
from uuid import uuid4
from traceback import format_exc

import arbiter
import requests

from control_tower.constants import *


def start_job(args=None):
    reports = {"backend": [], "ui": []}
    default_queues = {}
    cloud_queues = {}
    for test in args["tests"]:
        is_cloud_queue = False
        aws_settings = test["execution_json"].get("integrations").get("clouds", {}).get("aws_integration", None)
        if aws_settings:
            is_cloud_queue = True
            queue_name = str(uuid4())
            additional_settings = {
                "concurrency": test["execution_json"].get("concurrency"),
                "job_type": test["execution_json"].get("job_type"),
                "container_name": test["execution_json"].get("container")
            }
            cloud_queues[queue_name] = {"aws_settings": aws_settings, "settings": test["execution_json"]["cc_env_vars"],
                                        "additional_settings": additional_settings, "tasks": []}
        else:
            queue_name = test["location"]
            if queue_name not in default_queues.keys():
                default_queues[queue_name] = {"settings": test["execution_json"]["cc_env_vars"], "tasks": []}
        s3_settings = test["integrations"].get("system", {}).get("s3_integration", {})
        results_bucket = str(test["name"]).replace("_", "").replace(" ", "").lower()

        if "git" in test["source"]["name"]:
            artifact, bucket = _process_git_repo(test["execution_json"], test["build_id"], s3_settings)
        else:
            artifact = test["source"]["file_name"]
            bucket = test["source"]["bucket"]

        if test["job_type"] in {'perfgun', 'perfmeter'}:
            for i in range(test["parallel_runners"]):
                exec_params = loads(test["execution_json"]["execution_params"])
                exec_params['integrations'] = dumps(test["integrations"])
                exec_params['config_yaml'] = {}
                if LOKI_HOST:
                    exec_params['loki_host'] = LOKI_HOST
                    exec_params['loki_port'] = LOKI_PORT
                if ADDITIONAL_FILES:
                    exec_params['additional_files'] = ADDITIONAL_FILES

                if 'additional_files' in exec_params:
                    exec_params['additional_files'] = dumps(
                        exec_params['additional_files']).replace("'", "\"")
                if JVM_ARGS:
                    exec_params['JVM_ARGS'] = JVM_ARGS
                exec_params['build_id'] = test["build_id"]
                exec_params["test_name"] = test["name"]
                exec_params['DISTRIBUTED_MODE_PREFIX'] = DISTRIBUTED_MODE_PREFIX
                exec_params['galloper_url'] = GALLOPER_URL

                exec_params['bucket'] = bucket
                exec_params['artifact'] = artifact
                exec_params['results_bucket'] = results_bucket
                if globals().get("compile_and_run") == "true":
                    exec_params["compile_and_run"] = "true"
                exec_params['project_id'] = PROJECT_ID
                exec_params['token'] = TOKEN
                exec_params['report_id'] = test["REPORT_ID"]

                reports["backend"].append(test["REPORT_ID"])
                _update_test_status(status="Preparing...", percentage=5,
                                    description="We have enough workers to run the test. The test will start soon",
                                    report_id=test["REPORT_ID"])

                task_kwargs = {'job_type': str(test["job_type"]),
                               'container': test["execution_json"]["container"],
                               'execution_params': exec_params, 'job_name': test["name"]}

                if is_cloud_queue:
                    cloud_queues[queue_name]["tasks"].append(
                        arbiter.Task("execute", queue=queue_name, task_kwargs=task_kwargs))
                else:
                    default_queues[queue_name]["tasks"].append(
                        arbiter.Task("execute", queue=queue_name, task_kwargs=task_kwargs))

                post_processor_args = {
                    "galloper_url": GALLOPER_URL,
                    "project_id": PROJECT_ID,
                    "galloper_web_hook": GALLOPER_WEB_HOOK,
                    "report_id": test["REPORT_ID"],
                    "bucket": results_bucket,
                    "build_id": test["build_id"],
                    "prefix": DISTRIBUTED_MODE_PREFIX,
                    "token": TOKEN,
                    "integration": dumps(test["integrations"]),
                    "exec_params": dumps(exec_params),
                }
                if is_cloud_queue:
                    cloud_queues[queue_name]["tasks"].append(
                        arbiter.Task("post_process", queue=queue_name, task_kwargs=post_processor_args)
                    )
                else:
                    default_queues[queue_name]["tasks"].append(
                        arbiter.Task("post_process", queue=queue_name, task_kwargs=post_processor_args)
                    )
        else:
            exec_params = loads(test["execution_json"]["execution_params"])
            exec_params["GALLOPER_URL"] = GALLOPER_URL
            exec_params['project_id'] = PROJECT_ID
            exec_params["REPORTS_BUCKET"] = BUCKET
            exec_params["RESULTS_BUCKET"] = results_bucket
            exec_params["RESULTS_REPORT_NAME"] = DISTRIBUTED_MODE_PREFIX
            exec_params["GALLOPER_PROJECT_ID"] = PROJECT_ID
            exec_params["JOB_NAME"] = test["name"]
            exec_params['ARTIFACT'] = artifact
            exec_params['TESTS_BUCKET'] = bucket
            exec_params['integrations'] = dumps(test["integrations"])
            exec_params['report_id'] = test["REPORT_ID"]
            exec_params['REPORT_ID'] = test["REPORT_ID"]
            exec_params['token'] = TOKEN

            reports["ui"].append(test["REPORT_ID"])

            if mounts:
                exec_params['mounts'] = mounts if not exec_params["mounts"] \
                    else exec_params["mounts"]

            task_kwargs = {'job_type': str(test["job_type"]),
                           'container': test["execution_json"]["container"],
                           'execution_params': exec_params, 'job_name': test["name"]}

            if is_cloud_queue:
                cloud_queues[queue_name]["tasks"].append(
                    arbiter.Task("execute", queue=queue_name, task_kwargs=task_kwargs))
            else:
                default_queues[queue_name]["tasks"].append(
                    arbiter.Task("execute", queue=queue_name, task_kwargs=task_kwargs))

    try:
        if cloud_queues:
            _request_cloud_instances(cloud_queues)
            print("Instances started")
            _wait_for_interceptors_start(args, cloud_queues)
            print("Interceptors are ready")
            _start_tests(cloud_queues)
        if default_queues:
            _start_tests(default_queues)

        print("tests started")

        update_suite_status(status="In progress", percentage=10, description="All tests are started.",
                            report_id=args["suite_report_id"])
    except (NameError, KeyError) as e:
        print(e)
        update_suite_status(status="Failed", percentage=100, description=f"Failed to start tests for this suite. {e}",
                            report_id=args["suite_report_id"])
        raise e

    return default_queues, cloud_queues, reports


def _start_tests(queues):
    for each in queues.keys():
        arb = arbiter.Arbiter(host=queues[each]["settings"].get("RABBIT_HOST"),
                              port=queues[each]["settings"].get("RABBIT_PORT", 5672),
                              user=queues[each]["settings"].get("RABBIT_USER"),
                              password=queues[each]["settings"].get("RABBIT_PASSWORD"),
                              vhost=queues[each]["settings"].get("RABBIT_VHOST"),
                              timeout=120, use_ssl=RABBIT_USE_SSL, ssl_verify=RABBIT_SSL_VERIFY)
        group_id = arb.squad(queues[each]["tasks"])
        queues[each]["group_id"] = group_id
        queues[each]["arbiter"] = arb
        try:
            arb.close()
        except Exception as e:
            print(e)

def _request_cloud_instances(cloud_queues):
    print("_request_cloud_instances")
    from control_tower.cloud import create_aws_instances
    for each in cloud_queues.keys():
        cloud_queues[each]["finalizer_task"], cloud_queues[each]["instance_count"], cloud_queues[each]["fleet_id"],\
        cloud_queues[each]["launch_template_id"] = create_aws_instances(None, cloud_queues[each]["aws_settings"], True, each,
                                              cloud_queues[each]["additional_settings"])

def _wait_for_interceptors_start(args, cloud_queues, retry=10):
    print("wait for interceptors")

    while retry != 0:
        all_ready = all('state' in item and item['state'] == 'ready' for item in cloud_queues.values())
        if all_ready:
            break
        for each in cloud_queues.keys():
            arb = arbiter.Arbiter(host=cloud_queues[each]["settings"].get("RABBIT_HOST"),
                                  port=cloud_queues[each]["settings"].get("RABBIT_PORT", 5672),
                                  user=cloud_queues[each]["settings"].get("RABBIT_USER"),
                                  password=cloud_queues[each]["settings"].get("RABBIT_PASSWORD"),
                                  vhost=cloud_queues[each]["settings"].get("RABBIT_VHOST"),
                                  timeout=120, use_ssl=RABBIT_USE_SSL, ssl_verify=RABBIT_SSL_VERIFY)
            try:
                workers = arb.workers()
            except:
                workers = {}
            print(workers)
            try:
                arb.close()
            except Exception as e:
                print(e)
            if each in workers.keys() and workers[each]["available"] >= cloud_queues[each]["instance_count"]:
                print(f"Instances are ready for {each} queue")
                cloud_queues[each]["state"] = "ready"
            else:
                print("Waiting for instances to start ...")
        sleep(60)
        retry -= 1
        if retry == 0:
            print(f"Instances set up timeout - 600 seconds ...")
            _terminate_instances(cloud_queues)
            update_suite_status(status="Failed", percentage=100,
                                description=f"Couldn't set up cloud instances",
                                report_id=args["suite_report_id"])
            raise Exception("Couldn't set up cloud instances")

def _terminate_instances(cloud_queues):
    print("terminate cloud instances")
    from control_tower.cloud.aws import terminate_spot_instances
    for each in cloud_queues.keys():
        terminate_spot_instances(cloud_queues[each]["fleet_id"], cloud_queues[each]["launch_template_id"])


def _start_and_track(args=None):
    default_queues, cloud_queues, reports = start_job(args)
    print("Job started, waiting for containers to settle ... ")

    while not suite_finished(reports=reports):
        sleep(30)
        print("Check if suite is finished ...")
    print("Test suite is finished.")


def start_and_track_test_suite(args=None):
    try:
        _start_and_track(args)
        update_suite_status(status="Finished", percentage=100, description="Test suite is finished",
                            report_id=args["suite_report_id"])
    except:
        print(format_exc())
    finally:
        print("Done")
        #send_minio_dump_flag(status_code)

def _process_git_repo(test_config, test_build_id, s3_settings):
    from control_tower.git_clone import clone_repo, post_artifact
    git_setting = test_config["git"]
    clone_repo(git_setting, test_build_id=test_build_id)
    post_artifact(GALLOPER_URL, TOKEN, PROJECT_ID, f"{test_build_id}.zip", s3_settings, local_path=f"/tmp/git_dir/{test_build_id}")
    globals()["compile_and_run"] = "true"
    return f"{test_build_id}.zip", "tests"

def _update_test_status(status, percentage, description, report_id):
    module = "backend_performance"
    data = {"test_status": {"status": status, "percentage": percentage,
                            "description": description}}
    headers = {'content-type': 'application/json', 'Authorization': f'bearer {TOKEN}'}
    url = f'{GALLOPER_URL}/api/v1/{module}/report_status/{PROJECT_ID}/{report_id}'
    response = requests.put(url, json=data, headers=headers)
    try:
        print(response.json()["message"])
    except:
        print(response.text)

def update_suite_status(status, percentage, description, report_id):
    data = {"test_status": {"status": status, "percentage": percentage,
                            "description": description}}
    headers = {'content-type': 'application/json', 'Authorization': f'bearer {TOKEN}'}
    url = f'{GALLOPER_URL}/api/v1/performance_test_suite/report_status/{PROJECT_ID}/{report_id}'
    response = requests.put(url, json=data, headers=headers)
    try:
        print(response.json()["message"])
    except:
        print(response.text)

def suite_finished(reports):
    report_statuses = []
    headers = {'Authorization': f'bearer {TOKEN}'} if TOKEN else {}
    headers["Content-type"] = "application/json"
    for each in reports["backend"]:
        url = f'{GALLOPER_URL}/api/v1/backend_performance/report_status/{PROJECT_ID}/{each}'
        res = requests.get(url, headers=headers).json()
        report_statuses.append(res["message"].lower() in {
            "finished", "failed", "success",
            'canceled', 'cancelled', 'post processing (manual)',
            'error'
        })
    for each in reports["ui"]:
        url = f'{GALLOPER_URL}/api/v1/ui_performance/report_status/{PROJECT_ID}/{each}'
        res = requests.get(url, headers=headers).json()
        report_statuses.append(res["message"].lower() in {
            "finished", "failed", "success",
            'canceled', 'cancelled', 'post processing (manual)',
            'error'
        })

    return all(report_statuses)