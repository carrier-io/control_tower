import pytest
from time import time
from uuid import uuid4
from os import environ

environ["galloper_url"] = "http://example"
environ["RABBIT_HOST"] = "example"
environ["GALLOPER_WEB_HOOK"] = "http://example/hook"
environ["artifact"] = "test.zip"
environ["token"] = "test"
environ["project_id"] = "1"
environ["bucket"] = 'test'
environ["csv_path"] = "age.csv"
environ["lg_count"] = "5"

import mock
import requests_mock
import argparse
from control_tower.config_mock import BulkConfig
from control_tower import run


test_response = {"container": "getcarrier/perfmeter:beta-2.0-5.3",
                 "execution_params": "{\"cmd\": \"-n -t /mnt/jmeter/test.jmx -Jinflux.port=8086 "
                                     "-Jinflux.host=example -Jinflux.username=test "
                                     "-Jinflux.password=test "
                                     "-Jgalloper_url=https://example -Jinflux.db=test "
                                     "-Jtest_name=Flood -Jcomparison_db=comparison -Jtelegraf_db=telegraf "
                                     "-Jloki_host=http://example -Jloki_port=3100 -Jtest.type=default "
                                     "-JDURATION=60 -JVUSERS=10 -JRAMP_UP=30\","
                                     " \"cpu_cores_limit\": \"1\", "
                                     "\"memory_limit\": \"3\", "
                                     "\"influxdb_host\": \"example\", "
                                     "\"influxdb_user\": \"test\", "
                                     "\"influxdb_password\": \"test\", "
                                     "\"influxdb_comparison\": \"comparison\", "
                                     "\"influxdb_telegraf\": \"telegraf\", "
                                     "\"loki_host\": \"http://example\", "
                                     "\"loki_port\": \"3100\"}",
                 "cc_env_vars": {"RABBIT_HOST": "example",
                                 "RABBIT_USER": "test",
                                 "RABBIT_PASSWORD": "test",
                                 "RABBIT_VHOST": "test",
                                 "GALLOPER_WEB_HOOK": "https://example/task/1"},
                 "bucket": "tests",
                 "job_name": "test",
                 "artifact": "test.zip",
                 "job_type": "perfmeter",
                 "concurrency": 5,
                 "channel": "default",
                 "email": "True",
                 "email_recipients": "example@test.com"}
job_name = 'DemoTest'


class arbiterMock:
    def __init__(self, *args, **kwargs):
        self.squad_uuid = str(uuid4())

    def squad(self, *args, **kwargs):
        return self.squad_uuid


class bitter:
    def __init__(self, duration=10):
        self.start_time = time()
        self.duration = duration

    def status(self, *args, **kwargs):
        if time() - self.start_time > self.duration:
            return {'state': 'done'}
        return {'state': 'in progress'}

    def kill_group(self, *args, **kwargs):
        pass

    def close(self):
        pass

class taskMock:
    def __init__(self, *args, **kwargs):
        self.task_id = str(uuid4())


def test_str2bool():
    assert run.str2bool("true") is True
    assert run.str2bool("0") is False
    try:
        run.str2bool("zzz")
    except argparse.ArgumentTypeError as ex:
        assert str(ex) == 'Boolean value expected.'


def test_str2json():
    assert run.str2json("{}") == {}
    try:
        run.str2json("zzz")
    except argparse.ArgumentTypeError as ex:
        assert str(ex) == 'Json is not properly formatted.'


@mock.patch("arbiter.Arbiter")
@mock.patch("arbiter.Task")
def test_start_job(arbiterMock, taskMock):
    args = BulkConfig(
        bulk_container=[],
        bulk_params=[],
        job_type=[],
        job_name=job_name,
        bulk_concurrency=[],
        test_id=1
    )
    with requests_mock.Mocker() as req_mock:
        req_mock.get(f"{environ['galloper_url']}/api/v1/tests/{environ['project_id']}/backend/{args.test_id}",
                     json=test_response)
        req_mock.post(f"{environ['galloper_url']}/api/v1/tests/{environ['project_id']}/backend/{args.test_id}",
                     json=test_response)
        req_mock.get(f"{environ['galloper_url']}/api/v1/tests/{environ['project_id']}/{args.test_id}",
                     json={"job_type": "perfmeter"})
        req_mock.get(f"{environ['galloper_url']}/api/v1/project/{environ['project_id']}", text="custom")
        req_mock.post(f"{environ['galloper_url']}/api/v1/reports/{environ['project_id']}", json={"message": "patched"})
        args = run.append_test_config(args)
        assert all(key in args.execution_params[0] for key in ['cmd', 'cpu_cores_limit', 'memory_limit',
                                                               'influxdb_host', 'influxdb_user', 'influxdb_password',
                                                               'influxdb_comparison', 'influxdb_telegraf',
                                                               'loki_host', 'loki_port'])
        assert args.job_name == job_name
        arb, group_id, test_details = run.start_job(args)
        assert arb.squad.called
        assert len(arb.squad.call_args[0][0]) == int(environ["lg_count"])
        assert 'callback' in arb.squad.call_args[1]
        result = run.track_job(bitter(), str(uuid4()), args.test_id)
        assert result == 0
