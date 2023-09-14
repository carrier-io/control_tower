from json import loads
from os import environ
from uuid import uuid4

RABBIT_USER = environ.get('RABBIT_USER', 'user')
RABBIT_PASSWORD = environ.get('RABBIT_PASSWORD', 'password')
RABBIT_HOST = environ.get('RABBIT_HOST', 'localhost')
RABBIT_VHOST = environ.get('RABBIT_VHOST', 'carrier')
RABBIT_PORT = environ.get('RABBIT_PORT', '5672')
RABBIT_USE_SSL = environ.get("RABBIT_USE_SSL", "").lower() in ["true", "yes"]
RABBIT_SSL_VERIFY = environ.get("RABBIT_SSL_VERIFY", "").lower() in ["true", "yes"]
GALLOPER_WEB_HOOK = environ.get('GALLOPER_WEB_HOOK', None)
LOKI_HOST = environ.get('loki_host', None)
LOKI_PORT = environ.get('loki_port', '3100')
GALLOPER_URL = environ.get('galloper_url', None)
PROJECT_ID = environ.get('project_id', None)
REPORT_ID = environ.get('REPORT_ID', None)
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
CSV_FILES = loads(environ.get('csv_files', '{}'))
report_type = ""
JOB_TYPE_MAPPING = {
    "perfmeter": "jmeter",
    "perfgun": "gatling",
    "free_style": "other",
    "observer": "observer",
    "dast": "dast",
    "sast": "sast",
    "dependency": "dependency",
}
REPORT_TYPE_MAPPING = {
    "gatling": "backend",
    "jmeter": "backend",
    "observer": "frontend",
    "dast": "security",
    "sast": "security_sast",
    "dependency": "security_dependency",
}
CENTRY_MODULES_MAPPING = {
    "gatling": "backend_performance",
    "jmeter": "backend_performance",
    "observer": "ui_performance",
    "dast": "security",
    "sast": "security_sast",
    "dependency": "security_dependency",
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
    "RABBIT_VHOST": "RABBIT_VHOST",
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

CONTAINER_TAG = 'latest'
