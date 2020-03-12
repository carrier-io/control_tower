import os
from traceback import format_exc
from json import loads
from control_tower.config_mock import BulkConfig
from time import sleep


def parse_args(events):
    args = {
        "container": [],
        "execution_params": [],
        "job_type": [],
        "job_name": '',
        "concurrency": [],
        "channel": [],
        "artifact": [],
        "bucket": [],
        "save_reports": '',
        "junit": False,
        "quality_gate": False,
    }
    for event in events:
        args['container'].append(event["container"])
        args["execution_params"].append(loads(event['execution_params']))
        args["job_type"].append(event['job_type'])
        args["concurrency"].append(event['concurrency'])
        args["job_name"] = event.get('job_name', 'test')
        if "channel" in event:
            args["channel"].append(event["channel"])
        args["bucket"].append(event.get('bucket', ''))
        args["artifact"].append(event.get('artifact', ''))
        args["save_reports"] = event.get('save_reports', None)
        args["junit"] = event.get('junit', False)
        args["quality_gate"] = event.get('quality_gate', False)

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
        quality_gate=args["quality_gate"]
        )
    return args


def handler(event=None, context=None):
    try:
        os.mkdir('/tmp/reports')
        args = parse_args(event)
        from control_tower.run import start_job, track_job, process_junit_report
        groups = start_job(args)
        print("Job started, waiting for containers to settle ... ")
        for group in groups:
            track_job(group)
        if args.junit:
            process_junit_report(args)
        return {
            'statusCode': 200,
            'body': "test is done"
        }
    except:
        return {
            'statusCode': 500,
            'body': format_exc()
        }


# if __name__ == "__main__":
#     event = [
#         {
#             "container": "getcarrier/perfmeter:latest",
#             "execution_params": "{\"cmd\": \"-n -t /mnt/jmeter/FloodIO.jmx -Jbuild.id=distributed_1_1 -Jinflux.port=8086 -Jtest.type=distributed -Jinflux.db=jmeter -Jcomparison_db=comparison -Jenv.type=demo -Jinflux.host=192.168.1.193 -JVUSERS=10 -JDURATION=60 -JRAMP_UP=10 -Jtest_name=Flood\"}", \
#             "job_type": "perfmeter",
#             "job_name": "test",
#             "bucket": "jmeter",
#             "artifact": "Test.zip",
#             "concurrency": 2}]
#     print(handler(event))
