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
import requests
import requests_mock
import urllib3
import argparse
from control_tower.config_mock import BulkConfig
from control_tower import run


test_response = {"container": "getcarrier/perfmeter:latest-5.3",
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
                 "job_name": "DemoTest",
                 "artifact": {"file_name": "test.zip", "bucket": "tests"},
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
@mock.patch("control_tower.run.log_loki")
def test_start_job(arbiterMock, taskMock, mock_loki):
    args = BulkConfig(
        bulk_container=[],
        bulk_params=[],
        job_type=[],
        job_name=job_name,
        bulk_concurrency=[],
        test_id=1
    )
    with requests_mock.Mocker() as req_mock:
        req_mock.get(f"{environ['galloper_url']}/api/v1/shared/job_type/{environ['project_id']}/{args.test_id}",
                     json={"job_type": "perfmeter"})
        req_mock.post(f"{environ['galloper_url']}/api/v1/backend_performance/test/{environ['project_id']}/{args.test_id}",
                     json=test_response)
        req_mock.post(f"{environ['galloper_url']}/api/v1/backend_performance/reports/{environ['project_id']}",
                     json={"message": "patched", "id": 42})
        req_mock.put(f"{environ['galloper_url']}/api/v1/backend_performance/report_status/{environ['project_id']}/42",
                     json={"message": "ok"})
        req_mock.get(f"{environ['galloper_url']}/api/v1/backend_performance/report_status/{environ['project_id']}/42",
                     json={"message": "Finished"})
        req_mock.get(f"{environ['galloper_url']}/api/v1/backend_performance/report_status/{environ['project_id']}/{args.test_id}",
                     json={"message": "Finished"})
        args = run.append_test_config(args)
        assert all(key in args.execution_params[0] for key in ['cmd', 'cpu_cores_limit', 'memory_limit',
                                                               'influxdb_host', 'influxdb_user', 'influxdb_password',
                                                               'influxdb_comparison', 'influxdb_telegraf',
                                                               'loki_host', 'loki_port'])
        assert args.job_name == job_name
        arb, group_id, test_details = run.start_job(args)
        assert arb.squad.called
        # lg_count workers + 1 post_process task = lg_count + 1
        assert len(arb.squad.call_args[0][0]) == int(environ["lg_count"]) + 1
        result = run.track_job(bitter(), str(uuid4()), args.test_id)
        assert result == 0


# =============================================================================
# HTTP Timeout Hardening Tests
#
# Feature: _carrier_request wrapper that enforces a 120-second default timeout
# on every Carrier API call and raises SystemExit after 5 consecutive timeouts.
#
# ALL tests below MUST FAIL before the implementation is added to run.py.
# Expected failure mode: AttributeError — module 'control_tower.run' has no
# attribute '_carrier_request' (or '_CARRIER_REQUEST_TIMEOUT').
# =============================================================================


@pytest.fixture
def reset_timeout_counter():
    """Reset the module-level consecutive timeout counter around each test.

    Pre-implementation: _consecutive_timeout_count does not exist — fixture is
    a no-op so that the test body, not the fixture, produces the failure.
    Post-implementation: resets to 0 before and after each test to prevent
    counter state from bleeding between tests.
    """
    if hasattr(run, '_consecutive_timeout_count'):
        run._consecutive_timeout_count = 0
    yield
    if hasattr(run, '_consecutive_timeout_count'):
        run._consecutive_timeout_count = 0


# ---------------------------------------------------------------------------
# Level 4 — Packaging: new symbols must be importable from control_tower.run
# ---------------------------------------------------------------------------

def test_carrier_request_function_importable():
    assert hasattr(run, '_carrier_request'), (
        "_carrier_request is not defined in control_tower.run — "
        "the implementation has not been added yet."
    )


def test_carrier_timeout_constants_importable():
    assert hasattr(run, '_CARRIER_REQUEST_TIMEOUT'), (
        "_CARRIER_REQUEST_TIMEOUT is not defined in control_tower.run"
    )
    assert hasattr(run, '_CARRIER_MAX_CONSECUTIVE_TIMEOUTS'), (
        "_CARRIER_MAX_CONSECUTIVE_TIMEOUTS is not defined in control_tower.run"
    )


# ---------------------------------------------------------------------------
# Level 2 — Schema / Contract: constant values match the agreed SAD
# ---------------------------------------------------------------------------

def test_timeout_value_is_120():
    assert run._CARRIER_REQUEST_TIMEOUT == 120, (
        f"Expected _CARRIER_REQUEST_TIMEOUT == 120, "
        f"got {run._CARRIER_REQUEST_TIMEOUT!r}"
    )


def test_max_consecutive_timeouts_is_5():
    assert run._CARRIER_MAX_CONSECUTIVE_TIMEOUTS == 5, (
        f"Expected _CARRIER_MAX_CONSECUTIVE_TIMEOUTS == 5, "
        f"got {run._CARRIER_MAX_CONSECUTIVE_TIMEOUTS!r}"
    )


def test_carrier_request_sets_default_timeout(reset_timeout_counter):
    """When no timeout kwarg is passed, the outgoing request must use 120 s.

    _carrier_request calls requests.request(method, url, **kwargs) directly.
    mock.patch('requests.request') intercepts that attribute lookup on the
    requests module object — run.py accesses it as requests.request, so the
    patch is effective.
    """
    mock_response = mock.MagicMock()
    mock_response.status_code = 200
    with mock.patch('requests.request', return_value=mock_response) as mock_req:
        run._carrier_request('get', 'http://example.com/api/test')
    assert mock_req.called, "_carrier_request did not call requests.request"
    _, call_kwargs = mock_req.call_args
    assert call_kwargs.get('timeout') == 120, (
        f"Expected timeout=120 to be set by default, "
        f"got {call_kwargs.get('timeout')!r}"
    )


def test_carrier_request_explicit_timeout_wins(reset_timeout_counter):
    """When an explicit timeout kwarg is passed, setdefault must NOT override it."""
    mock_response = mock.MagicMock()
    mock_response.status_code = 200
    with mock.patch('requests.request', return_value=mock_response) as mock_req:
        run._carrier_request('get', 'http://example.com/api/test', timeout=999)
    _, call_kwargs = mock_req.call_args
    assert call_kwargs.get('timeout') == 999, (
        f"Expected explicit timeout=999 to be preserved by setdefault, "
        f"got {call_kwargs.get('timeout')!r}"
    )


# ---------------------------------------------------------------------------
# Level 1 — Unit: pure logic, no live HTTP
# ---------------------------------------------------------------------------

def test_consecutive_timeout_counter_increments(reset_timeout_counter):
    """Each Timeout exception must increment _consecutive_timeout_count by 1."""
    with mock.patch(
        'requests.request',
        side_effect=requests.exceptions.Timeout("simulated timeout"),
    ):
        with pytest.raises(requests.exceptions.Timeout):
            run._carrier_request('get', 'http://example.com/api/test')
    assert run._consecutive_timeout_count == 1, (
        f"Expected counter == 1 after one timeout, "
        f"got {run._consecutive_timeout_count!r}"
    )


def test_consecutive_timeout_counter_resets_on_success(reset_timeout_counter):
    """A successful 200 response must reset _consecutive_timeout_count to 0."""
    run._consecutive_timeout_count = 3
    mock_response = mock.MagicMock()
    mock_response.status_code = 200
    with mock.patch('requests.request', return_value=mock_response):
        run._carrier_request('get', 'http://example.com/api/test')
    assert run._consecutive_timeout_count == 0, (
        f"Expected counter reset to 0 after success, "
        f"got {run._consecutive_timeout_count!r}"
    )


def test_five_consecutive_timeouts_raises_systemexit(reset_timeout_counter):
    """Exactly 5 consecutive timeouts must raise SystemExit on the 5th call."""
    with mock.patch(
        'requests.request',
        side_effect=requests.exceptions.Timeout("simulated timeout"),
    ):
        for _ in range(4):
            with pytest.raises(requests.exceptions.Timeout):
                run._carrier_request('get', 'http://example.com/api/test')
        with pytest.raises(SystemExit):
            run._carrier_request('get', 'http://example.com/api/test')


def test_systemexit_message_content(reset_timeout_counter):
    """The SystemExit message must contain the agreed human-readable text."""
    run._consecutive_timeout_count = 4
    with mock.patch(
        'requests.request',
        side_effect=requests.exceptions.Timeout("simulated timeout"),
    ):
        with pytest.raises(SystemExit) as exc_info:
            run._carrier_request('get', 'http://example.com/api/test')
    message = str(exc_info.value)
    assert 'Test did not finish' in message, (
        f"Expected 'Test did not finish' in SystemExit message, got: {message!r}"
    )
    assert 'Carrier platform is unresponsive' in message, (
        f"Expected 'Carrier platform is unresponsive' in SystemExit message, "
        f"got: {message!r}"
    )


def test_critical_log_on_fifth_timeout(reset_timeout_counter):
    """logger.critical must be called exactly once on the 5th consecutive timeout."""
    run._consecutive_timeout_count = 4
    with mock.patch(
        'requests.request',
        side_effect=requests.exceptions.Timeout("simulated timeout"),
    ):
        with mock.patch.object(run, 'logger') as mock_logger:
            with pytest.raises(SystemExit):
                run._carrier_request('get', 'http://example.com/api/test')
    mock_logger.critical.assert_called_once()
    critical_msg = mock_logger.critical.call_args[0][0]
    assert '5 consecutive timeouts' in critical_msg, (
        f"Expected '5 consecutive timeouts' in critical log message, "
        f"got: {critical_msg!r}"
    )


def test_warning_log_on_each_timeout(reset_timeout_counter):
    """logger.warning must be called with the platform-unavailable message on every timeout."""
    with mock.patch(
        'requests.request',
        side_effect=requests.exceptions.Timeout("simulated timeout"),
    ):
        with mock.patch.object(run, 'logger') as mock_logger:
            with pytest.raises(requests.exceptions.Timeout):
                run._carrier_request('get', 'http://example.com/api/test')
    mock_logger.warning.assert_called_once()
    warning_msg = mock_logger.warning.call_args[0][0]
    assert 'unavailable' in warning_msg.lower(), (
        f"Expected 'unavailable' in warning message, got: {warning_msg!r}"
    )


def test_readtimeout_error_is_handled(reset_timeout_counter):
    """urllib3.exceptions.ReadTimeoutError must be caught by _carrier_request.

    The wrapper's except clause covers both requests.exceptions.Timeout and
    urllib3.exceptions.ReadTimeoutError. This test exercises the urllib3 path.
    The exception must be re-raised (or escalated to SystemExit if counter >= 5),
    and the counter must be incremented.
    """
    read_timeout_exc = urllib3.exceptions.ReadTimeoutError(
        None, 'http://example.com/api/test', 'Read timed out.'
    )
    with mock.patch('requests.request', side_effect=read_timeout_exc):
        with pytest.raises((urllib3.exceptions.ReadTimeoutError, SystemExit)):
            run._carrier_request('get', 'http://example.com/api/test')
    assert run._consecutive_timeout_count >= 1, (
        f"Expected counter >= 1 after ReadTimeoutError, "
        f"got {run._consecutive_timeout_count!r}"
    )


# ---------------------------------------------------------------------------
# Level 3 — Fixture-based Integration (mock HTTP, no live Carrier calls)
#
# Strategy: patch requests.Session.request (the universal sink for ALL requests
# calls — both old-style requests.put/get and the new requests.request path)
# to capture the timeout kwarg without making real network connections.
#
# Pre-implementation:  calls requests.put(..., timeout=30, ...) → assertion
#                      fails because 30 != 120.
# Post-implementation: calls _carrier_request → requests.request(..., timeout=120, ...)
#                      → Session.request captures timeout=120 → assertion passes.
# ---------------------------------------------------------------------------

def test_update_test_status_uses_120s_timeout(reset_timeout_counter):
    """update_test_status must forward timeout=120 to the HTTP layer via _carrier_request."""
    mock_response = mock.MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {'message': 'ok'}
    with mock.patch.object(run, 'REPORT_ID', '42'), \
         mock.patch.object(requests.Session, 'request', return_value=mock_response) as mock_session_req:
        run.update_test_status(status='Running', percentage=50, description='integration test')
    assert mock_session_req.called, "update_test_status did not make any HTTP request"
    # Session.request is an unbound method — self is the first positional arg.
    # method/url are passed as keyword args by requests.api.request, so they
    # appear in call_args[1] alongside timeout.
    timeout_used = mock_session_req.call_args[1].get('timeout')
    assert timeout_used == 120, (
        f"update_test_status must use timeout=120 (via _carrier_request), "
        f"got timeout={timeout_used!r}"
    )


def test_test_finished_uses_120s_timeout(reset_timeout_counter):
    """test_finished must forward timeout=120 to the HTTP layer via _carrier_request."""
    mock_response = mock.MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {'message': 'Finished'}
    with mock.patch.object(requests.Session, 'request', return_value=mock_response) as mock_session_req:
        run.test_finished(report_id='42')
    assert mock_session_req.called, "test_finished did not make any HTTP request"
    timeout_used = mock_session_req.call_args[1].get('timeout')
    assert timeout_used == 120, (
        f"test_finished must use timeout=120 (via _carrier_request), "
        f"got timeout={timeout_used!r}"
    )


def test_counter_shared_across_calls(reset_timeout_counter):
    """The timeout counter is module-level state shared across all call sites.

    Two consecutive Timeout exceptions from different URL paths must produce
    _consecutive_timeout_count == 2, confirming the counter is not per-call-site.
    """
    with mock.patch(
        'requests.request',
        side_effect=requests.exceptions.Timeout("simulated timeout"),
    ):
        with pytest.raises(requests.exceptions.Timeout):
            run._carrier_request('get', 'http://example.com/api/endpoint1')
        with pytest.raises(requests.exceptions.Timeout):
            run._carrier_request('post', 'http://example.com/api/endpoint2')
    assert run._consecutive_timeout_count == 2, (
        f"Expected counter == 2 after two consecutive timeouts from different "
        f"endpoints, got {run._consecutive_timeout_count!r}"
    )

