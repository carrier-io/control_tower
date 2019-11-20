from traceback import format_exc
from json import loads
from control_tower.config_mock import BulkConfig

def parse_args(events):
    args = {
        "container": [],
        "execution_params": [],
        "job_type": [],
        "job_name": [],
        "concurrency": [],
        "channel": []
    }
    for event in events:
        args['container'].append(event["container"])
        args["execution_params"].append(loads(event['execution_params']))
        args["job_type"].append(event['job_type'])
        args["job_name"].append(event.get('job_name', ''))
        args["concurrency"].append(event['concurrency'])
        if "channel" in event:
            args["channel"].append(event["channel"])
    args = BulkConfig(
        bulk_container=args['container'], 
        bulk_params=args["execution_params"], 
        job_type=args["job_type"],
        job_name=args["job_name"], 
        bulk_concurrency=args["concurrency"], 
        channels=args["channel"]
        )
    return args


def handler(event=None, context=None):
    try:
        args = parse_args(event)
        group_id = start_job(args)
        sleep(60)
        track_job(group_id=group_id)
        return {
            'statusCode': 200,
            'body': "test is done"
        }
    except:
        return {
            'statusCode': 500,
            'body': format_exc()
        }


if __name__ == "__main__":
    handler()
