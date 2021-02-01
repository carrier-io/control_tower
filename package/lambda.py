import os
from traceback import format_exc
from json import loads
from control_tower.config_mock import BulkConfig


def parse_args(events):
    args = {
        "container": [],
        "execution_params": [],
        "job_type": [],
        "job_name": '',
        "concurrency": [],
        "channel": [],
        "artifact": "",
        "bucket": "",
        "save_reports": False,
        "junit": False,
        "quality_gate": False,
        "jira": False,
        "report_portal": False,
        "email": False,
        "email_recipients": "",
        "azure_devops": False,
        "deviation": 0,
        "max_deviation": 0,
        "test_id": ""
    }
    for event in events:
        if "container" in event:
            args["container"].append(event["container"])
        if "execution_params" in event:
            args["execution_params"].append(loads(event["execution_params"]))
        if "job_type" in event:
            args["job_type"].append(event["job_type"])
        if "concurrency" in event:
            args["concurrency"].append(event["concurrency"])
        if "channel" in event:
            args["channel"].append(event["channel"])
        args["job_name"] = event.get('job_name', 'test')
        args["bucket"] = event.get('bucket', '')
        args["artifact"] = event.get('artifact', '')
        args["save_reports"] = event.get('save_reports', False)
        args["junit"] = event.get('junit', False)
        args["quality_gate"] = event.get('quality_gate', False)
        args["jira"] = event.get('jira', False)
        args["report_portal"] = event.get('report_portal', False)
        args["email"] = event.get('email', False)
        args["email_recipients"] = event.get('email_recipients', "")
        args["azure_devops"] = event.get('azure_devops', False)
        args["deviation"] = event.get('deviation', 0)
        args["max_deviation"] = event.get('max_deviation', 0)
        args["test_id"] = event.get('test_id', '')
        env_vars = event.get("cc_env_vars", None)
        if env_vars:
            for key, value in env_vars.items():
                os.environ[key] = value

    args = BulkConfig(
        bulk_container=args['container'],
        bulk_params=args["execution_params"],
        job_type=args["job_type"],
        job_name=args["job_name"],
        bulk_concurrency=args["concurrency"],
        channel=args["channel"],
        bucket=args["bucket"],
        artifact=args["artifact"],
        save_reports=args["save_reports"],
        junit=args["junit"],
        quality_gate=args["quality_gate"],
        deviation=args["deviation"],
        max_deviation=args["max_deviation"],
        report_path="/tmp/reports",
        test_id=args["test_id"],
        jira=args["jira"],
        report_portal=args["report_portal"],
        email=args["email"],
        azure_devops=args["azure_devops"],
        email_recipients=args["email_recipients"]
        )
    if args.test_id:
        from control_tower.run import append_test_config
        args = append_test_config(args)
    else:
        from control_tower.run import str2bool, process_git_repo, split_csv_file
        if "git" in events[0]:
            process_git_repo(events[0], args)
        if str2bool(os.environ.get('split_csv', 'False')):
            split_csv_file(args)
    return args


def handler(event=None, context=None):
    try:
        if not os.path.exists('/tmp/reports'):
            os.mkdir('/tmp/reports')
        args = parse_args(event)
        from control_tower.run import _start_and_track
        _start_and_track(args)
        return {
            'statusCode': 200,
            'body': "test is done"
        }
    except:
        return {
            'statusCode': 500,
            'body': format_exc()
        }
