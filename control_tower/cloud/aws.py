import base64
from uuid import uuid4

import arbiter
import boto3

from control_tower.cloud.common import wait_for_instances_start, get_instance_init_script, \
    get_instances_requirements, get_instances_requirements_for_suite
from control_tower.run import logger

ec2 = None


def create_aws_instances(args, aws_config, is_suite=False, queue_name=None, settings=None):
    logger.info("Requesting Spot Fleets...")
    if is_suite and queue_name:
        print("Request instances for test suite")
        cpu, instance_count, memory = get_instances_requirements_for_suite(settings, aws_config, queue_name)
    else:
        queue_name = str(uuid4())
        cpu, instance_count, memory = get_instances_requirements(args, aws_config, queue_name)
    finalizer_queue_name = str(uuid4())



    global ec2
    ec2 = boto3.client('ec2', aws_access_key_id=aws_config.get("aws_access_key"),
                       aws_secret_access_key=aws_config["aws_secret_access_key"],
                       region_name=aws_config["region_name"])

    if is_suite:
        user_data = get_instance_init_script(settings["container_name"], cpu, finalizer_queue_name, memory, queue_name, instance_count)
    else:
        user_data = get_instance_init_script(args.container[0], cpu, finalizer_queue_name, memory, queue_name,
                                             instance_count)
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
            "BlockDeviceMappings": [
                {
                    "DeviceName": "/dev/sda1",
                    "Ebs": {
                        "VolumeSize": 25,
                        "DeleteOnTermination": True,
                        "VolumeType": "gp2"
                    },
                }
            ]
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
        logger.error(res)
        try:
            error_msg = res["Warning"]["Errors"][0]["Message"]
        except (KeyError, IndexError):
            error_msg = "Error while creating launch template"
        raise Exception(error_msg)

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
        try:
            error_msg = res["Errors"][0]["ErrorMessage"]
        except (KeyError, IndexError):
            error_msg = "Error while creating spot fleet"
        raise Exception(error_msg)

    if not is_suite:
        wait_for_instances_start(
            args, instance_count,
            lambda: terminate_spot_instances(fleet_id, launch_template_id)
        )

    ec2_settings = {
        "aws_access_key_id": aws_config.get("aws_access_key"),
        "aws_secret_access_key": aws_config["aws_secret_access_key"],
        "region_name": aws_config["region_name"],
        "fleet_id": fleet_id,
        "launch_template_id": launch_template_id,
    }
    finalizer_task = arbiter.Task("terminate_ec2_instances", queue=finalizer_queue_name,
                                  task_type="finalize", task_kwargs=ec2_settings)
    if is_suite:
        return finalizer_task, instance_count, fleet_id, launch_template_id
    else:
        return finalizer_task


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
