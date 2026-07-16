# Tests for download_report feature — written BEFORE implementation (TDD RED phase)
# SAD: docs/superpowers/specs/2026-07-13-control-tower-download-report-sad.md

import os
import argparse

os.environ.setdefault("galloper_url", "http://example")
os.environ.setdefault("RABBIT_HOST", "example")
os.environ.setdefault("GALLOPER_WEB_HOOK", "http://example/hook")
os.environ.setdefault("artifact", "test.zip")
os.environ.setdefault("token", "test-token")
os.environ.setdefault("project_id", "1")
os.environ.setdefault("bucket", "test")
os.environ.setdefault("build_id", "build_f8f3bd85-bde2-4205-ae67-8235f715b821")
os.environ.setdefault("PREFIX", "test_results_build_f8f3bd85-bde2-4205-ae67-8235f715b821_")

import pytest
import mock
import requests_mock as req_mock_module

from control_tower import run
from control_tower.constants import GALLOPER_URL, PROJECT_ID, DISTRIBUTED_MODE_PREFIX, BUILD_ID


# ---------------------------------------------------------------------------
# 1. CLI flag: --download_report exists and defaults to False
# ---------------------------------------------------------------------------

def test_download_report_flag_defaults_to_false():
    """arg_parse() must expose --download_report defaulting to False."""
    args = run.arg_parse()
    assert hasattr(args, "download_report"), (
        "--download_report argument not found in arg_parse()"
    )
    assert args.download_report is False, (
        "Default value of --download_report must be False for backward compatibility"
    )


def test_download_report_flag_accepts_true():
    """str2bool wiring: --download_report=True must parse to Python True."""
    import sys
    orig = sys.argv[:]
    try:
        sys.argv = ["run", "--download_report", "true"]
        args = run.arg_parse()
        assert args.download_report is True
    finally:
        sys.argv = orig


def test_download_report_flag_accepts_false_string():
    """str2bool wiring: --download_report=false must parse to Python False."""
    import sys
    orig = sys.argv[:]
    try:
        sys.argv = ["run", "--download_report", "false"]
        args = run.arg_parse()
        assert args.download_report is False
    finally:
        sys.argv = orig


# ---------------------------------------------------------------------------
# 2. DOWNLOAD_REPORT env var exposed in constants
# ---------------------------------------------------------------------------

def test_download_report_constant_exists():
    """DOWNLOAD_REPORT constant must be importable from control_tower.constants."""
    from control_tower import constants
    assert hasattr(constants, "DOWNLOAD_REPORT"), (
        "DOWNLOAD_REPORT env-var constant not found in constants.py"
    )


def test_download_report_constant_default_false():
    """DOWNLOAD_REPORT must default to False when env var is not set."""
    import importlib
    import control_tower.constants as consts
    # The constant was already evaluated at import time with our env setup (not set)
    # Just verify it's a bool False (or falsy) when env var absent
    assert not consts.DOWNLOAD_REPORT or os.environ.get("DOWNLOAD_REPORT", "").lower() in (
        "true", "yes", "1", "t"
    ), "DOWNLOAD_REPORT should default to False when env var is absent"


# ---------------------------------------------------------------------------
# 3. download_gatling_report: finds ZIP by prefix in bucket listing
# ---------------------------------------------------------------------------

def test_download_gatling_report_returns_response_when_zip_found():
    """download_gatling_report must return a Response when a matching ZIP exists."""
    bucket = "contentstackmixed"
    build_id = "build_f8f3bd85-bde2-4205-ae67-8235f715b821"
    prefix = f"test_results_{build_id}_"
    zip_name = f"reports_{prefix}Lg_529_2039.zip"
    zip_bytes = b"PK\x03\x04fake_zip_content"

    with req_mock_module.Mocker() as m:
        # Mock the bucket listing endpoint
        list_url = f"{GALLOPER_URL}/api/v1/artifacts/artifacts/{PROJECT_ID}/{bucket}"
        m.get(list_url, json={"total": 3, "files": [
            f"build_{build_id}.log",
            f"build_{build_id}.csv.gz",
            zip_name,
        ]})
        # Mock the file download endpoint
        dl_url = f"{GALLOPER_URL}/api/v1/artifacts/artifact/{PROJECT_ID}/{bucket}/{zip_name}"
        m.get(dl_url, content=zip_bytes, status_code=200)

        result = run.download_gatling_report(
            s3_settings={},
            results_bucket=bucket,
            distributed_mode_prefix=prefix,
            retry=3,
        )

    assert result is not None, "Expected a Response object, got None"
    assert result.status_code == 200
    assert result.content == zip_bytes


def test_download_gatling_report_handles_rows_response_format():
    """download_gatling_report must work when the listing API returns 'rows' dicts (Carrier 2026 API)."""
    bucket = "contentstackmixed"
    build_id = "build_f8f3bd85-bde2-4205-ae67-8235f715b821"
    prefix = f"test_results_{build_id}_"
    zip_name = f"reports_{prefix}Lg_529_2039.zip"
    zip_bytes = b"PK\x03\x04rows_format_zip"

    with req_mock_module.Mocker() as m:
        list_url = f"{GALLOPER_URL}/api/v1/artifacts/artifacts/{PROJECT_ID}/{bucket}"
        # The 2026 Carrier API returns {"rows": [{"name": "...", "size": "...", "modified": "..."}], "total": N}
        m.get(list_url, json={"total": 3, "rows": [
            {"name": f"build_{build_id}.log", "size": "1K", "modified": "2026-07-13T10:00:00Z"},
            {"name": f"build_{build_id}.csv.gz", "size": "10K", "modified": "2026-07-13T10:00:00Z"},
            {"name": zip_name, "size": "1.6M", "modified": "2026-07-13T10:15:00Z"},
        ]})
        dl_url = f"{GALLOPER_URL}/api/v1/artifacts/artifact/{PROJECT_ID}/{bucket}/{zip_name}"
        m.get(dl_url, content=zip_bytes, status_code=200)

        result = run.download_gatling_report(
            s3_settings={},
            results_bucket=bucket,
            distributed_mode_prefix=prefix,
            retry=1,
        )

    assert result is not None, "Expected a Response object with rows format, got None"
    assert result.content == zip_bytes


def test_download_gatling_report_returns_none_when_no_zip_found():
    """download_gatling_report must return None (non-fatal) when no matching ZIP exists."""
    bucket = "emptyresults"
    prefix = "test_results_build_aabbccdd_"

    with req_mock_module.Mocker() as m:
        list_url = f"{GALLOPER_URL}/api/v1/artifacts/artifacts/{PROJECT_ID}/{bucket}"
        m.get(list_url, json={"total": 1, "files": ["some_other_file.xml"]})

        result = run.download_gatling_report(
            s3_settings={},
            results_bucket=bucket,
            distributed_mode_prefix=prefix,
            retry=1,
        )

    assert result is None, "Expected None when no matching ZIP found, got a Response"


def test_download_gatling_report_retries_on_empty_listing():
    """download_gatling_report must retry when listing returns no matching file."""
    bucket = "slowresults"
    prefix = "test_results_build_retry_test_"
    zip_name = f"reports_{prefix}Lg_100_200.zip"
    zip_bytes = b"PK\x03\x04zip_after_retry"

    call_count = {"n": 0}

    def list_handler(request, context):
        call_count["n"] += 1
        if call_count["n"] < 2:
            # First call: not ready yet
            return {"total": 0, "files": []}
        # Second call: ZIP is ready
        return {"total": 1, "files": [zip_name]}

    with req_mock_module.Mocker() as m:
        list_url = f"{GALLOPER_URL}/api/v1/artifacts/artifacts/{PROJECT_ID}/{bucket}"
        m.get(list_url, json=list_handler)
        dl_url = f"{GALLOPER_URL}/api/v1/artifacts/artifact/{PROJECT_ID}/{bucket}/{zip_name}"
        m.get(dl_url, content=zip_bytes, status_code=200)

        with mock.patch("control_tower.run.sleep"):  # avoid real sleep in tests
            result = run.download_gatling_report(
                s3_settings={},
                results_bucket=bucket,
                distributed_mode_prefix=prefix,
                retry=3,
            )

    assert result is not None
    assert result.content == zip_bytes
    assert call_count["n"] == 2, f"Expected 2 listing calls (1 retry), got {call_count['n']}"


def test_download_gatling_report_selects_first_match_in_multi_lg_run():
    """When multiple ZIPs exist (multi-LG run), download_gatling_report downloads the first one."""
    bucket = "multilgresults"
    prefix = "test_results_build_multi_uuid_"
    zip1 = f"reports_{prefix}Lg_100_200.zip"
    zip2 = f"reports_{prefix}Lg_300_400.zip"

    with req_mock_module.Mocker() as m:
        list_url = f"{GALLOPER_URL}/api/v1/artifacts/artifacts/{PROJECT_ID}/{bucket}"
        m.get(list_url, json={"total": 2, "files": [zip1, zip2]})
        dl_url = f"{GALLOPER_URL}/api/v1/artifacts/artifact/{PROJECT_ID}/{bucket}/{zip1}"
        m.get(dl_url, content=b"zip1_content", status_code=200)

        result = run.download_gatling_report(
            s3_settings={},
            results_bucket=bucket,
            distributed_mode_prefix=prefix,
            retry=1,
        )

    assert result is not None
    assert result.content == b"zip1_content"


# ---------------------------------------------------------------------------
# 4. process_gatling_report: writes file to report_path
# ---------------------------------------------------------------------------

def test_process_gatling_report_writes_zip_to_report_path(tmp_path):
    """process_gatling_report must write the downloaded ZIP to args.report_path."""
    import types

    bucket = "contentstackmixed"
    build_id = "build_f8f3bd85-bde2-4205-ae67-8235f715b821"
    prefix = f"test_results_{build_id}_"
    zip_name = f"reports_{prefix}Lg_529_2039.zip"
    zip_bytes = b"PK\x03\x04real_zip_data"

    args = types.SimpleNamespace(
        job_name="ContentStack_Mixed",
        report_path=str(tmp_path),
        download_report=True,
    )

    with mock.patch.object(run, 'BUILD_ID', build_id):
        with req_mock_module.Mocker() as m:
            list_url = f"{GALLOPER_URL}/api/v1/artifacts/artifacts/{PROJECT_ID}/{bucket}"
            m.get(list_url, json={"total": 1, "files": [zip_name]})
            dl_url = f"{GALLOPER_URL}/api/v1/artifacts/artifact/{PROJECT_ID}/{bucket}/{zip_name}"
            m.get(dl_url, content=zip_bytes, status_code=200)

            run.process_gatling_report(args, s3_settings={})

    written = list(tmp_path.iterdir())
    assert len(written) == 1, f"Expected 1 file written, got {len(written)}: {written}"
    assert written[0].name == zip_name
    assert written[0].read_bytes() == zip_bytes


def test_process_gatling_report_does_not_raise_when_zip_not_found(tmp_path):
    """process_gatling_report must not raise when ZIP is unavailable (non-fatal)."""
    import types

    args = types.SimpleNamespace(
        job_name="EmptyTest",
        report_path=str(tmp_path),
        download_report=True,
    )

    with mock.patch('control_tower.run.sleep'):
        with req_mock_module.Mocker() as m:
            list_url = f"{GALLOPER_URL}/api/v1/artifacts/artifacts/{PROJECT_ID}/emptytest"
            m.get(list_url, json={"total": 0, "files": []})

            # Must not raise — non-fatal by design
            run.process_gatling_report(args, s3_settings={})

    # No file written is acceptable
    assert list(tmp_path.iterdir()) == []


# ---------------------------------------------------------------------------
# 5. save_reports implicit override
# ---------------------------------------------------------------------------

def test_save_reports_implicitly_set_when_download_report_is_true():
    """When download_report=True and save_reports=False, _start_and_track must force save_reports=True."""
    import types

    args = types.SimpleNamespace(
        download_report=True,
        save_reports=False,
        job_type=["perfgun"],
        job_name="test",
        report_path="/tmp/reports",
        integrations={},
        artifact="",
        concurrency=[1],
        container=["getcarrier/perfgun:latest"],
        channel=["default"],
        execution_params=[{}],
        deviation=0,
        max_deviation=0,
        test_id="",
    )

    # Patch everything that _start_and_track calls so we can observe the save_reports override
    with mock.patch.object(run, "start_job") as mock_start, \
         mock.patch.object(run, "track_job", return_value=0), \
         mock.patch.object(run, "process_gatling_report") as mock_dl, \
         mock.patch.object(run, "send_minio_dump_flag"):

        mock_start.return_value = (mock.Mock(), "group_id", {"id": "123"})

        # Simulate the status check so track_job exits immediately
        with mock.patch.object(run, "test_finished", return_value=True):
            try:
                run._start_and_track(args)
            except Exception:
                pass  # We only care about the save_reports mutation, not full execution

    # After _start_and_track runs its implicit override, args.save_reports must be True
    assert args.save_reports is True, (
        "save_reports must be implicitly set to True when download_report=True"
    )


def test_save_reports_not_changed_when_download_report_is_false():
    """When download_report=False, save_reports must remain unchanged (False)."""
    import types

    args = types.SimpleNamespace(
        download_report=False,
        save_reports=False,
        job_type=["perfgun"],
        job_name="test",
        report_path="/tmp/reports",
        integrations={},
        artifact="",
        concurrency=[1],
        container=["getcarrier/perfgun:latest"],
        channel=["default"],
        execution_params=[{}],
        deviation=0,
        max_deviation=0,
        test_id="",
    )

    with mock.patch.object(run, "start_job") as mock_start, \
         mock.patch.object(run, "track_job", return_value=0), \
         mock.patch.object(run, "send_minio_dump_flag"):

        mock_start.return_value = (mock.Mock(), "group_id", {})
        with mock.patch.object(run, "test_finished", return_value=True):
            try:
                run._start_and_track(args)
            except Exception:
                pass

    assert args.save_reports is False, (
        "save_reports must NOT be changed when download_report=False"
    )


# ---------------------------------------------------------------------------
# 6. _start_and_track calls process_gatling_report for perfgun/perfmeter
# ---------------------------------------------------------------------------

def test_start_and_track_calls_process_gatling_report_for_perfgun(tmp_path):
    """_start_and_track must call process_gatling_report when download_report=True and job_type=perfgun."""
    import types

    args = types.SimpleNamespace(
        download_report=True,
        save_reports=False,
        job_type=["perfgun"],
        job_name="test",
        report_path=str(tmp_path),
        integrations={},
        artifact="",
        concurrency=[1],
        container=["getcarrier/perfgun:latest"],
        channel=["default"],
        execution_params=[{}],
        deviation=0,
        max_deviation=0,
        test_id="",
    )

    with mock.patch.object(run, "start_job") as mock_start, \
         mock.patch.object(run, "track_job", return_value=0), \
         mock.patch.object(run, "process_gatling_report") as mock_dl, \
         mock.patch.object(run, "send_minio_dump_flag"), \
         mock.patch.object(run, "test_finished", return_value=True):

        mock_start.return_value = (mock.Mock(), "group_id", {"id": "123"})
        try:
            run._start_and_track(args)
        except Exception:
            pass

    assert mock_dl.called, (
        "process_gatling_report must be called when download_report=True and job_type=perfgun"
    )


def test_start_and_track_skips_process_gatling_report_when_flag_false(tmp_path):
    """_start_and_track must NOT call process_gatling_report when download_report=False."""
    import types

    args = types.SimpleNamespace(
        download_report=False,
        save_reports=False,
        job_type=["perfgun"],
        job_name="test",
        report_path=str(tmp_path),
        integrations={},
        artifact="",
        concurrency=[1],
        container=["getcarrier/perfgun:latest"],
        channel=["default"],
        execution_params=[{}],
        deviation=0,
        max_deviation=0,
        test_id="",
    )

    with mock.patch.object(run, "start_job") as mock_start, \
         mock.patch.object(run, "track_job", return_value=0), \
         mock.patch.object(run, "process_gatling_report") as mock_dl, \
         mock.patch.object(run, "send_minio_dump_flag"), \
         mock.patch.object(run, "test_finished", return_value=True):

        mock_start.return_value = (mock.Mock(), "group_id", {})
        try:
            run._start_and_track(args)
        except Exception:
            pass

    assert not mock_dl.called, (
        "process_gatling_report must NOT be called when download_report=False"
    )


def test_start_and_track_skips_process_gatling_report_for_observer(tmp_path):
    """_start_and_track must NOT call process_gatling_report when job_type=observer (no ZIP)."""
    import types

    args = types.SimpleNamespace(
        download_report=True,
        save_reports=False,
        job_type=["observer"],
        job_name="test",
        report_path=str(tmp_path),
        integrations={},
        artifact="",
        concurrency=[1],
        container=["getcarrier/observer:latest"],
        channel=["default"],
        execution_params=[{}],
        deviation=0,
        max_deviation=0,
        test_id="",
    )

    with mock.patch.object(run, "start_job") as mock_start, \
         mock.patch.object(run, "track_job", return_value=0), \
         mock.patch.object(run, "process_gatling_report") as mock_dl, \
         mock.patch.object(run, "send_minio_dump_flag"), \
         mock.patch.object(run, "test_finished", return_value=True):

        mock_start.return_value = (mock.Mock(), "group_id", {})
        try:
            run._start_and_track(args)
        except Exception:
            pass

    assert not mock_dl.called, (
        "process_gatling_report must NOT be called for observer job type"
    )


# ---------------------------------------------------------------------------
# 7. append_test_config propagates download_report from test config JSON
# ---------------------------------------------------------------------------

def test_append_test_config_propagates_download_report():
    """append_test_config must propagate download_report=True from test config JSON."""
    from control_tower.config_mock import BulkConfig

    test_config_response = {
        "container": "getcarrier/perfgun:latest",
        "execution_params": '{"GATLING_TEST_PARAMS": "-Dtest_type=demo -Denv_type=demo"}',
        "cc_env_vars": {
            "RABBIT_HOST": "example", "RABBIT_USER": "u",
            "RABBIT_PASSWORD": "p", "RABBIT_VHOST": "v",
        },
        "bucket": "tests",
        "job_name": "GatlingTest",
        "artifact": {"file_name": "test.zip", "bucket": "tests"},
        "job_type": "perfgun",
        "concurrency": 1,
        "channel": "default",
        "download_report": "True",  # Set in test config JSON
        "save_reports": "False",
    }

    args = BulkConfig(
        bulk_container=[],
        bulk_params=[],
        job_type=[],
        job_name="GatlingTest",
        bulk_concurrency=[],
        test_id=42,
    )

    with req_mock_module.Mocker() as m:
        base = os.environ["galloper_url"]
        pid = os.environ["project_id"]
        m.get(f"{base}/api/v1/shared/job_type/{pid}/42",
              json={"job_type": "perfgun"})
        m.post(f"{base}/api/v1/backend_performance/test/{pid}/42",
               json=test_config_response)

        args = run.append_test_config(args)

    assert hasattr(args, "download_report"), "download_report not set on args by append_test_config"
    assert args.download_report is True, (
        f"Expected download_report=True from test config, got {args.download_report}"
    )


# ---------------------------------------------------------------------------
# 8. FIX 1: DOWNLOAD_REPORT env-var is wired as argparse default
# ---------------------------------------------------------------------------

def test_download_report_env_var_default_wired_to_argparse():
    """arg_parse() must pick up DOWNLOAD_REPORT=True from env without any CLI flag.

    Patches control_tower.run.DOWNLOAD_REPORT to True and controls sys.argv so
    no explicit -dr flag is passed. If argparse uses DOWNLOAD_REPORT as the default,
    args.download_report must be True even with an empty command line.
    """
    import sys
    orig_argv = sys.argv[:]
    try:
        sys.argv = ["run"]
        with mock.patch.object(run, 'DOWNLOAD_REPORT', True):
            args = run.arg_parse()
    finally:
        sys.argv = orig_argv
    assert args.download_report is True, (
        "arg_parse() must return download_report=True when DOWNLOAD_REPORT constant is True "
        "and no -dr CLI flag is passed (env-var default not wired into argparse)"
    )


# ---------------------------------------------------------------------------
# 9. download_lighthouse_report: finds HTML by suffix in reports bucket listing
# ---------------------------------------------------------------------------

def test_download_lighthouse_report_returns_response_when_html_found():
    """download_lighthouse_report must return (filename, response) when a matching HTML file exists."""
    html_name = "some_run_id_user-flow.report.html"
    html_bytes = b"<html>lighthouse report</html>"

    with req_mock_module.Mocker() as m:
        list_url = f"{GALLOPER_URL}/api/v1/artifacts/artifacts/{PROJECT_ID}/reports"
        m.get(list_url, json={"total": 2, "files": [
            "some_run_id.json",
            html_name,
        ]})
        dl_url = f"{GALLOPER_URL}/api/v1/artifacts/artifact/{PROJECT_ID}/reports/{html_name}"
        m.get(dl_url, content=html_bytes, status_code=200)

        filename, response = run.download_lighthouse_report(s3_settings={}, retry=1)

    assert filename == html_name, f"Expected filename '{html_name}', got '{filename}'"
    assert response is not None, "Expected a Response object, got None"
    assert response.status_code == 200
    assert response.content == html_bytes


def test_download_lighthouse_report_takes_last_match_when_multiple_html_files():
    """download_lighthouse_report must return the LAST matching HTML file when multiple exist."""
    html1 = "run_001_user-flow.report.html"
    html2 = "run_002_user-flow.report.html"
    html3 = "run_003_user-flow.report.html"
    expected_content = b"<html>latest lighthouse report</html>"

    with req_mock_module.Mocker() as m:
        list_url = f"{GALLOPER_URL}/api/v1/artifacts/artifacts/{PROJECT_ID}/reports"
        m.get(list_url, json={"total": 3, "files": [html1, html2, html3]})
        # Only the last one should be downloaded
        dl_url = f"{GALLOPER_URL}/api/v1/artifacts/artifact/{PROJECT_ID}/reports/{html3}"
        m.get(dl_url, content=expected_content, status_code=200)

        with mock.patch("control_tower.run.sleep"):
            filename, response = run.download_lighthouse_report(s3_settings={}, retry=1)

    assert filename == html3, (
        f"Expected last match '{html3}', got '{filename}'"
    )
    assert response.content == expected_content


def test_download_lighthouse_report_returns_none_when_no_html_found():
    """download_lighthouse_report must return (None, None) when no _user-flow.report.html exists."""
    with req_mock_module.Mocker() as m:
        list_url = f"{GALLOPER_URL}/api/v1/artifacts/artifacts/{PROJECT_ID}/reports"
        m.get(list_url, json={"total": 1, "files": ["some_run.json"]})

        with mock.patch("control_tower.run.sleep"):
            filename, response = run.download_lighthouse_report(s3_settings={}, retry=1)

    assert filename is None, f"Expected None filename when no HTML found, got '{filename}'"
    assert response is None, f"Expected None response when no HTML found, got {response}"


def test_download_lighthouse_report_retries_on_empty_listing():
    """download_lighthouse_report must retry and succeed when HTML appears on second listing call."""
    html_name = "run_late_user-flow.report.html"
    html_bytes = b"<html>late lighthouse report</html>"
    call_count = {"n": 0}

    def list_handler(request, context):
        call_count["n"] += 1
        if call_count["n"] < 2:
            return {"total": 0, "files": []}
        return {"total": 1, "files": [html_name]}

    with req_mock_module.Mocker() as m:
        list_url = f"{GALLOPER_URL}/api/v1/artifacts/artifacts/{PROJECT_ID}/reports"
        m.get(list_url, json=list_handler)
        dl_url = f"{GALLOPER_URL}/api/v1/artifacts/artifact/{PROJECT_ID}/reports/{html_name}"
        m.get(dl_url, content=html_bytes, status_code=200)

        with mock.patch("control_tower.run.sleep"):
            filename, response = run.download_lighthouse_report(s3_settings={}, retry=3)

    assert filename == html_name
    assert response is not None
    assert response.content == html_bytes
    assert call_count["n"] == 2, (
        f"Expected 2 listing calls (1 retry), got {call_count['n']}"
    )


# ---------------------------------------------------------------------------
# 10. process_lighthouse_report: writes file to report_path
# ---------------------------------------------------------------------------

def test_process_lighthouse_report_writes_html_to_report_path(tmp_path):
    """process_lighthouse_report must write the downloaded HTML to args.report_path / filename."""
    import types

    html_name = "observer_run_user-flow.report.html"
    html_bytes = b"<html>lighthouse</html>"

    args = types.SimpleNamespace(
        job_name="LighthouseTest",
        report_path=str(tmp_path),
        download_report=True,
    )

    fake_response = mock.Mock()
    fake_response.content = html_bytes

    with mock.patch.object(run, "download_lighthouse_report", return_value=(html_name, fake_response)):
        run.process_lighthouse_report(args, s3_settings={})

    written = list(tmp_path.iterdir())
    assert len(written) == 1, f"Expected 1 file written, got {len(written)}: {written}"
    assert written[0].name == html_name
    assert written[0].read_bytes() == html_bytes


def test_process_lighthouse_report_does_not_raise_when_not_found(tmp_path):
    """process_lighthouse_report must not raise when no HTML report is available (non-fatal)."""
    import types

    args = types.SimpleNamespace(
        job_name="EmptyObserverTest",
        report_path=str(tmp_path),
        download_report=True,
    )

    with mock.patch.object(run, "download_lighthouse_report", return_value=(None, None)):
        # Must not raise — non-fatal by design
        run.process_lighthouse_report(args, s3_settings={})

    assert list(tmp_path.iterdir()) == [], "No file must be written when report not found"


# ---------------------------------------------------------------------------
# 11. _start_and_track calls process_lighthouse_report for observer
# ---------------------------------------------------------------------------

def test_start_and_track_calls_process_lighthouse_report_for_observer(tmp_path):
    """_start_and_track must call process_lighthouse_report when download_report=True and job_type=observer."""
    import types

    args = types.SimpleNamespace(
        download_report=True,
        save_reports=False,
        job_type=["observer"],
        job_name="LighthouseObserverTest",
        report_path=str(tmp_path),
        integrations={},
        artifact="",
        concurrency=[1],
        container=["getcarrier/observer:latest"],
        channel=["default"],
        execution_params=[{}],
        deviation=0,
        max_deviation=0,
        test_id="",
    )

    with mock.patch.object(run, "start_job") as mock_start, \
         mock.patch.object(run, "track_job", return_value=0), \
         mock.patch.object(run, "process_lighthouse_report") as mock_lh, \
         mock.patch.object(run, "process_gatling_report") as mock_gat, \
         mock.patch.object(run, "send_minio_dump_flag"), \
         mock.patch.object(run, "test_finished", return_value=True):

        mock_start.return_value = (mock.Mock(), "group_id", {"id": "123"})
        try:
            run._start_and_track(args)
        except Exception:
            pass

    assert mock_lh.called, (
        "process_lighthouse_report must be called when download_report=True and job_type=observer"
    )
    assert not mock_gat.called, (
        "process_gatling_report must NOT be called for observer job type"
    )


def test_start_and_track_does_not_call_process_lighthouse_for_perfgun(tmp_path):
    """_start_and_track must call process_gatling_report and NOT process_lighthouse_report for perfgun."""
    import types

    args = types.SimpleNamespace(
        download_report=True,
        save_reports=False,
        job_type=["perfgun"],
        job_name="GatlingTest",
        report_path=str(tmp_path),
        integrations={},
        artifact="",
        concurrency=[1],
        container=["getcarrier/perfgun:latest"],
        channel=["default"],
        execution_params=[{}],
        deviation=0,
        max_deviation=0,
        test_id="",
    )

    with mock.patch.object(run, "start_job") as mock_start, \
         mock.patch.object(run, "track_job", return_value=0), \
         mock.patch.object(run, "process_lighthouse_report") as mock_lh, \
         mock.patch.object(run, "process_gatling_report") as mock_gat, \
         mock.patch.object(run, "send_minio_dump_flag"), \
         mock.patch.object(run, "test_finished", return_value=True):

        mock_start.return_value = (mock.Mock(), "group_id", {"id": "123"})
        try:
            run._start_and_track(args)
        except Exception:
            pass

    assert mock_gat.called, (
        "process_gatling_report must be called when download_report=True and job_type=perfgun"
    )
    assert not mock_lh.called, (
        "process_lighthouse_report must NOT be called for perfgun job type"
    )


# ---------------------------------------------------------------------------
# 12. save_reports override is gated to perfgun/perfmeter (not observer)
# ---------------------------------------------------------------------------

def test_save_reports_NOT_overridden_for_observer_job_type(tmp_path):
    """When download_report=True, save_reports=False, job_type=observer: save_reports must remain False.

    Observer (Lighthouse) uploads its HTML via a different mechanism — it does not
    need save_reports=True. Forcing it True for observer is a behavioral regression.
    """
    import types

    args = types.SimpleNamespace(
        download_report=True,
        save_reports=False,
        job_type=["observer"],
        job_name="LighthouseObserverTest",
        report_path=str(tmp_path),
        integrations={},
        artifact="",
        concurrency=[1],
        container=["getcarrier/observer:latest"],
        channel=["default"],
        execution_params=[{}],
        deviation=0,
        max_deviation=0,
        test_id="",
    )

    with mock.patch.object(run, "start_job") as mock_start, \
         mock.patch.object(run, "track_job", return_value=0), \
         mock.patch.object(run, "process_lighthouse_report"), \
         mock.patch.object(run, "send_minio_dump_flag"), \
         mock.patch.object(run, "test_finished", return_value=True):

        mock_start.return_value = (mock.Mock(), "group_id", {"id": "123"})
        try:
            run._start_and_track(args)
        except Exception:
            pass

    assert args.save_reports is False, (
        "save_reports must NOT be forced to True for observer job type when download_report=True "
        "(observer's Lighthouse HTML does not require save_reports)"
    )


def test_save_reports_IS_overridden_for_perfgun_job_type(tmp_path):
    """When download_report=True, save_reports=False, job_type=perfgun: save_reports must become True.

    Gatling requires save_reports=True to upload the ZIP that download_gatling_report
    then retrieves. This override must remain active for perfgun/perfmeter.
    """
    import types

    args = types.SimpleNamespace(
        download_report=True,
        save_reports=False,
        job_type=["perfgun"],
        job_name="GatlingTest",
        report_path=str(tmp_path),
        integrations={},
        artifact="",
        concurrency=[1],
        container=["getcarrier/perfgun:latest"],
        channel=["default"],
        execution_params=[{}],
        deviation=0,
        max_deviation=0,
        test_id="",
    )

    with mock.patch.object(run, "start_job") as mock_start, \
         mock.patch.object(run, "track_job", return_value=0), \
         mock.patch.object(run, "process_gatling_report"), \
         mock.patch.object(run, "send_minio_dump_flag"), \
         mock.patch.object(run, "test_finished", return_value=True):

        mock_start.return_value = (mock.Mock(), "group_id", {"id": "123"})
        try:
            run._start_and_track(args)
        except Exception:
            pass

    assert args.save_reports is True, (
        "save_reports must be forced to True for perfgun when download_report=True "
        "(Gatling ZIP must be uploaded before it can be downloaded)"
    )
