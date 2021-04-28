import boto3
import base64
from json import loads, JSONDecodeError
import requests
from time import sleep
from uuid import uuid4
from arbiter import Arbiter


ec2 = None


def request_spot_fleets(args, galloper_url, project_id, token, rabbit_host, rabbit_user, rabbit_password, rabbit_port,
                        vhost):
    print("Requesting Spot Fleets...")
    secrets_url = f"{galloper_url}/api/v1/secrets/{project_id}/aws"
    headers = {
        'Authorization': f'bearer {token}',
        'Content-type': 'application/json'
    }
    aws_config = {}
    try:
        aws_config = loads(requests.get(secrets_url, headers=headers).json()["secret"])
    except (AttributeError, JSONDecodeError):
        print("Failed to load AWS config for the project")
        exit(1)
    queue_name = str(uuid4())
    finalizer_queue_name = str(uuid4())
    total_workers = 0
    cpu = float(args.execution_params[0]["cpu_cores_limit"]) if "cpu_cores_limit" in args.execution_params[0] else 1.0
    memory = int(args.execution_params[0]["memory_limit"]) if "memory_limit" in args.execution_params[0] else 1
    for i in range(len(args.concurrency)):
        args.channel[i] = queue_name
        args.execution_params[i]["JVM_ARGS"] = f"-Xms{memory}g -Xmx{memory}g"
        total_workers += args.concurrency[i]
    cpu += 0.5
    memory += 1
    if cpu > 8:
        print("Max CPU cores limit should be less then 8")
        exit(1)
    if memory > 30:
        print("Max memory limit should be less then 30g")
        exit(1)
    total_cpu_cores = round(cpu * total_workers + 0.1)
    workers_per_lg = 2 if total_cpu_cores > 2 and memory < 8 else 1
    lg_count = round(total_workers / workers_per_lg + 0.1)
    print(f"CPU per worker - {cpu}. Memory per worker - {memory}g")
    print(f"Instances count - {lg_count}")
    global ec2
    ec2 = boto3.client('ec2', aws_access_key_id=aws_config.get("aws_access_key"),
                       aws_secret_access_key=aws_config["aws_secret_access_key"], region_name=aws_config["region_name"])
    user_data = '''#!/bin/bash
    apt update
    apt install docker
    apt install docker.io -y
    '''
    user_data += f"docker pull {args.container[0]}\n"
    user_data += f"docker run -d -v /var/run/docker.sock:/var/run/docker.sock -e RAM_QUOTA=1g -e CPU_QUOTA=1" \
                 f" -e CPU_CORES=1 -e RABBIT_HOST={rabbit_host} -e RABBIT_USER={rabbit_user}" \
                 f" -e RABBIT_PASSWORD={rabbit_password} -e VHOST={vhost} -e QUEUE_NAME={finalizer_queue_name}" \
                 f" -e LOKI_HOST={galloper_url.replace('https://', 'http://')} " \
                 f"getcarrier/interceptor:latest\n"
    user_data += f"docker run -d -v /var/run/docker.sock:/var/run/docker.sock -e RAM_QUOTA={memory}g -e CPU_QUOTA={cpu}" \
                 f" -e CPU_CORES={workers_per_lg} -e RABBIT_HOST={rabbit_host} -e RABBIT_USER={rabbit_user}" \
                 f" -e RABBIT_PASSWORD={rabbit_password} -e VHOST={vhost} -e QUEUE_NAME={queue_name}" \
                 f" -e LOKI_HOST={galloper_url.replace('https://', 'http://')} " \
                 f"getcarrier/interceptor:latest"
    user_data = base64.b64encode(user_data.encode("ascii")).decode("ascii")
    config = {
        "Type": "request",
        'AllocationStrategy': "lowestPrice",
        "IamFleetRole": aws_config["iam_fleet_role"],
        "TargetCapacity": lg_count,
        "SpotPrice": "2.5",
        "TerminateInstancesWithExpiration": True,
        'LaunchSpecifications': []
    }

    instance_types = get_instance_types(cpu, memory, workers_per_lg)
    for each in instance_types:
        specs = {
            "ImageId": aws_config["image_id"],
            "InstanceType": each,
            "BlockDeviceMappings": [],
            "SpotPrice": "2.5",
            "NetworkInterfaces": [],
            "SecurityGroups": [],
            "UserData": user_data
            }
        if aws_config["security_groups"]:
            for sg in aws_config["security_groups"].split(","):
                specs["SecurityGroups"].append({"GroupId": sg})
        config["LaunchSpecifications"].append(specs)
    response = ec2.request_spot_fleet(SpotFleetRequestConfig=config)
    print("*********************************************")
    print(response)
    fleet_id = response["SpotFleetRequestId"]
    arbiter = Arbiter(host=rabbit_host, port=rabbit_port, user=rabbit_user, password=rabbit_password, vhost=vhost)
    retry = 10
    while retry != 0:
        try:
            workers = arbiter.workers()
        except:
            workers = {}
        print(workers)
        if args.channel[0] in workers and workers[args.channel[0]]["available"] >= total_workers:
            print("Spot Fleet instances are ready")
            break
        else:
            print("Waiting for the Spot Fleet instances to start ...")
            sleep(60)
            retry -= 1
            if retry == 0:
                print("Spot instances set up timeout - 600 seconds ...")
                terminate_spot_instances(fleet_id)
                exit(1)
    ec2_settings = {
        "aws_access_key_id": aws_config.get("aws_access_key"),
        "aws_secret_access_key": aws_config["aws_secret_access_key"],
        "region_name": aws_config["region_name"],
        "fleet_id": fleet_id,
        "finalizer_queue_name": finalizer_queue_name
    }
    return ec2_settings


def terminate_spot_instances(fleet_id):
    print("Terminating Spot instances...")
    global ec2
    response = ec2.cancel_spot_fleet_requests(
        SpotFleetRequestIds=[
            fleet_id,
        ],
        TerminateInstances=True
    )
    print(response)


def get_instance_types(cpu, memory, workers_per_lg):
    instances = {
        "2 cpu": {
            "4g": ["c5.large", "t2.medium", "t3a.medium", "t3.medium"],
            "8g": ["m5n.large", "m5zn.large", "m5.large", "t2.large", "t3.large"],
            "16g": ["r4.large", "r5n.large", "r5ad.large", "r5.large", "r5d.large"]
        },
        "4 cpu": {
            "8g": ["c5a.xlarge", "c5.xlarge", "c5d.xlarge", "c5ad.xlarge"],
            "16g": ["m5ad.xlarge", "m5d.xlarge", "m5zn.xlarge", "m5.xlarge", "m5a.xlarge"]
        },
        "8 cpu": {
            "16g": ["c5.2xlarge", "c5ad.2xlarge", "c5a.2xlarge", "c5n.2xlarge"],
            "32g": ["m4.2xlarge", "m5dn.2xlarge", "m5ad.2xlarge", "m5d.2xlarge"]
        }
    }

    if cpu * workers_per_lg < 2:
        cpu_key = "2 cpu"
    elif cpu * workers_per_lg < 4:
        cpu_key = "4 cpu"
    else:
        cpu_key = "8 cpu"

    if memory * workers_per_lg < 4 and cpu_key == "2 cpu":
        memory_key = "4g"
    elif memory * workers_per_lg < 8:
        memory_key = "8g"
    elif memory * workers_per_lg < 16:
        memory_key = "16g"
    else:
        memory_key = "32g"
        cpu_key = "8 cpu"

    print(f"Instance types for {cpu_key} and {memory_key}:")
    print(instances[cpu_key][memory_key])
    return instances[cpu_key][memory_key]
