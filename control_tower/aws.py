import base64
from time import sleep
from uuid import uuid4

import boto3
from arbiter import Arbiter

from control_tower.run import logger

ec2 = None


def request_spot_fleets(args, aws_config, galloper_url, rabbit_host, rabbit_user,
        rabbit_password, rabbit_port, vhost
):
    logger.info("Requesting Spot Fleets...")
    queue_name = str(uuid4())
    finalizer_queue_name = str(uuid4())
    instance_count = 0

    cpu = max(2, int(aws_config["cpu_cores_limit"]))
    memory = int(aws_config["memory_limit"]) + 1

    for i in range(len(args.concurrency)):
        args.channel[i] = queue_name
        instance_count += args.concurrency[i]

    if cpu > 8:
        logger.error("Max CPU cores limit should be less then 8")
        raise Exception
    if memory > 16:
        logger.error("Max memory limit should be less then 16g")
        raise Exception

    logger.info(f"CPU per instance - {cpu}. Memory per instance - {memory}g")
    logger.info(f"Instances count - {instance_count}")

    global ec2
    ec2 = boto3.client('ec2', aws_access_key_id=aws_config.get("aws_access_key"),
                       aws_secret_access_key=aws_config["aws_secret_access_key"],
                       region_name=aws_config["region_name"])

    user_data = '''#!/bin/bash
    
    apt update -y
    apt install docker -y
    apt install docker.io -y
    '''
    user_data += f"docker pull {args.container[0]}\n"
    user_data += f"docker run -d -v /var/run/docker.sock:/var/run/docker.sock -e RAM_QUOTA=1g -e CPU_QUOTA=1" \
                 f" -e CPU_CORES=1 -e RABBIT_HOST={rabbit_host} -e RABBIT_USER={rabbit_user}" \
                 f" -e RABBIT_PASSWORD={rabbit_password} -e VHOST={vhost} -e QUEUE_NAME={finalizer_queue_name}" \
                 f" -e LOKI_HOST={galloper_url.replace('https://', 'http://')} " \
                 f"getcarrier/interceptor:latest\n"
    user_data += f"docker run -d -v /var/run/docker.sock:/var/run/docker.sock -e RAM_QUOTA={memory}g -e CPU_QUOTA={cpu * 0.9}" \
                 f" -e CPU_CORES=1 -e RABBIT_HOST={rabbit_host} -e RABBIT_USER={rabbit_user}" \
                 f" -e RABBIT_PASSWORD={rabbit_password} -e VHOST={vhost} -e QUEUE_NAME={queue_name}" \
                 f" -e LOKI_HOST={galloper_url.replace('https://', 'http://')} " \
                 f"getcarrier/interceptor:latest"
    user_data = base64.b64encode(user_data.encode("ascii")).decode("ascii")
    launch_template_config = {
        "LaunchTemplateName": f"{queue_name}",
        "LaunchTemplateData": {
            "ImageId": aws_config["image_id"] or get_default_image_id(),
            "UserData": user_data,
            "InstanceRequirements": {
                'VCpuCount': {
                    'Min': cpu,
                },
                'MemoryMiB': {
                    'Min': memory * 1024,
                },
            },
        }
    }

    if aws_config["security_groups"]:
        launch_template_config["LaunchTemplateData"]["SecurityGroups"] = aws_config[
            "security_groups"].split(",")
    if aws_config["key_name"]:
        launch_template_config["LaunchTemplateData"]["KeyName"] = aws_config["key_name"]


    res = ec2.create_launch_template(**launch_template_config)
    logger.info(res)

    launch_template_id = res["LaunchTemplate"]["LaunchTemplateId"]

    if res.get("Warning"):
        terminate_spot_instances(template_id=launch_template_id)
        raise Exception(res["Warning"]["Errors"][0]["Message"])

    is_spot_request = aws_config["instance_type"] == "spot"

    fleet_config = {
        "Type": "instant",
        "SpotOptions": {
            'AllocationStrategy': 'lowest-price'
        },
        "LaunchTemplateConfigs": [{
            'LaunchTemplateSpecification': {
                'LaunchTemplateId': launch_template_id,
                'Version': '$Default'
            },
            "Overrides": [{
                "MaxPrice": "2.5",
            }]
        }],
        "TargetCapacitySpecification": {
            'TotalTargetCapacity': instance_count,
            'OnDemandTargetCapacity': instance_count if not is_spot_request else 0,
            'SpotTargetCapacity': instance_count if is_spot_request else 0,
            'DefaultTargetCapacityType': aws_config["instance_type"]
        },
    }
    if aws_config["subnet_id"]:
        fleet_config["LaunchTemplateConfigs"][0]["Overrides"][0].update({
            "SubnetId": aws_config["subnet_id"]
        })

    logger.info(f"final fleet_config {fleet_config}")
    response = ec2.create_fleet(**fleet_config)
    logger.info("*********************************************")
    logger.info(response)

    fleet_id = response["FleetId"]

    if response.get("Errors"):
        terminate_spot_instances(fleet_id, launch_template_id)
        raise Exception(res["Errors"][0]["ErrorMessage"])

    arbiter = Arbiter(host=rabbit_host, port=rabbit_port, user=rabbit_user,
                      password=rabbit_password, vhost=vhost)
    retry = 10
    while retry != 0:
        try:
            workers = arbiter.workers()
        except:
            workers = {}
        logger.info(workers)
        if args.channel[0] in workers \
                and workers[args.channel[0]]["available"] >= instance_count:
            logger.info("Spot Fleet instances are ready")
            break
        else:
            logger.info("Waiting for the Spot Fleet instances to start ...")
            sleep(60)
            retry -= 1
            if retry == 0:
                logger.info("Spot instances set up timeout - 600 seconds ...")
                terminate_spot_instances(fleet_id, launch_template_id)
                exit(1)
    ec2_settings = {
        "aws_access_key_id": aws_config.get("aws_access_key"),
        "aws_secret_access_key": aws_config["aws_secret_access_key"],
        "region_name": aws_config["region_name"],
        "fleet_id": fleet_id,
        "launch_template_id": launch_template_id,
        "finalizer_queue_name": finalizer_queue_name
    }
    logger.info(f"ec2_settings: {ec2_settings}")
    return ec2_settings


def terminate_spot_instances(fleet_id: str = "", template_id: str = ""):
    logger.info("Terminating Spot instances...")
    global ec2
    if fleet_id:
        response = ec2.delete_fleets(
            FleetIds=[
                fleet_id,
            ],
            TerminateInstances=True
        )
        logger.info(response)
    if template_id:
        response = ec2.delete_launch_template(
            LaunchTemplateId=template_id
        )
        logger.info(response)


def get_default_image_id() -> str:
    """
    Finds Ubuntu 22.04 LTS image in aws catalog

    :return: ami id of image
    """
    global ec2
    res = ec2.describe_images(
        Owners=['amazon'],
        Filters=[
            {
                'Name': 'description',
                'Values': ['*Canonical, Ubuntu, 22.04 LTS*']
            },
            {
                'Name': 'architecture',
                'Values': ['x86_64']
            },
            {
                'Name': 'image-type',
                'Values': ['machine']
            },
            {
                'Name': 'owner-alias',
                'Values': ['amazon']
            }
        ],
    )
    return res['Images'][0]['ImageId']
