from time import sleep
from typing import Callable
from os import environ

from arbiter import Arbiter

from control_tower.constants import RABBIT_HOST, RABBIT_PORT, RABBIT_USER, RABBIT_PASSWORD, \
    RABBIT_VHOST, GALLOPER_URL, CONTAINER_TAG, RABBIT_USE_SSL, RABBIT_SSL_VERIFY
from control_tower.run import logger


def get_instances_requirements_for_suite(settings, cloud_config, queue_name):
    cpu = max(2, int(cloud_config["cpu_cores_limit"]))
    memory = int(cloud_config["memory_limit"]) + 1
    instance_count = settings["concurrency"]

    if settings["job_type"] in ['perfgun', 'perfmeter']:
        if instance_count == 1:
            cpu += 1
            memory += 4
        else:
            instance_count += 1
    if cpu > 8:
        logger.error("Max CPU cores limit should be less then 8")
        raise Exception
    if memory > 16:
        logger.error("Max memory limit should be less then 16g")
        raise Exception
    logger.info(f"CPU per instance - {cpu}. Memory per instance - {memory}g")
    logger.info(f"Instances count - {instance_count}")
    return cpu, instance_count, memory


def get_instances_requirements(args, cloud_config, queue_name):
    instance_count = 0
    cpu = max(2, int(cloud_config["cpu_cores_limit"]))
    memory = int(cloud_config["memory_limit"]) + 1
    for i in range(len(args.concurrency)):
        args.channel[i] = queue_name
        instance_count += args.concurrency[i]

    if args.job_type[0] in ['perfgun', 'perfmeter']:
        if instance_count == 1:
            cpu += 1
            memory += 4
        else:
            instance_count += 1
    if cpu > 8:
        logger.error("Max CPU cores limit should be less then 8")
        raise Exception
    if memory > 16:
        logger.error("Max memory limit should be less then 16g")
        raise Exception
    logger.info(f"CPU per instance - {cpu}. Memory per instance - {memory}g")
    logger.info(f"Instances count - {instance_count}")
    return cpu, instance_count, memory


def wait_for_instances_start(args, instance_count: int, terminate_instance_func: Callable):
    try:
        arbiter = Arbiter(host=environ.get("RABBIT_HOST"), port=5672, user=environ.get("RABBIT_USER"),
                          password=environ.get("RABBIT_PASSWORD"), vhost=environ.get("RABBIT_VHOST"), timeout=120,
                          use_ssl=RABBIT_USE_SSL, ssl_verify=RABBIT_SSL_VERIFY)
    except:
        terminate_instance_func()
        raise Exception("Couldn't connect to RabbitMQ")
    retry = 10
    while retry != 0:
        try:
            workers = arbiter.workers()
        except:
            workers = {}
        logger.info(workers)
        if args.channel[0] in workers \
                and workers[args.channel[0]]["available"] >= instance_count:
            logger.info("Instances are ready")
            break
        else:
            logger.info("Waiting for instances to start ...")
            sleep(60)
            retry -= 1
            if retry == 0:
                logger.info(f"Instances set up timeout - {60 * retry} seconds ...")
                terminate_instance_func()
                raise Exception("Couldn't set up cloud instances")


def get_instance_init_script(container_name, cpu, finalizer_queue_name, memory, queue_name, instance_count=None):
    if instance_count and instance_count == 1:
        cpu_cores = 2
        memory -= 4
        cpu -= 1
    else:
        cpu_cores = 1
    user_data = '''#!/bin/bash

    apt update -y
    apt install docker -y
    apt install docker.io -y
    '''
    user_data += f"docker pull {container_name}\n"
    user_data += f"docker pull getcarrier/performance_results_processing:{CONTAINER_TAG}\n"
    user_data += f"docker run -d -v /var/run/docker.sock:/var/run/docker.sock -e RAM_QUOTA=1g -e CPU_QUOTA=1" \
                 f" -e CPU_CORES=1 -e RABBIT_HOST={environ.get('RABBIT_HOST')} -e RABBIT_USER={environ.get('RABBIT_USER')}" \
                 f" -e RABBIT_PASSWORD={environ.get('RABBIT_PASSWORD')} -e VHOST={environ.get('RABBIT_VHOST')} -e QUEUE_NAME={finalizer_queue_name}" \
                 f" -e LOKI_HOST={GALLOPER_URL.replace('https://', 'http://')} " \
                 f"getcarrier/interceptor:{CONTAINER_TAG}\n"
    user_data += f"docker run -d -v /var/run/docker.sock:/var/run/docker.sock -e RAM_QUOTA={memory}g -e CPU_QUOTA={cpu * 0.9}" \
                 f" -e CPU_CORES={cpu_cores} -e RABBIT_HOST={environ.get('RABBIT_HOST')} -e RABBIT_USER={environ.get('RABBIT_USER')}" \
                 f" -e RABBIT_PASSWORD={environ.get('RABBIT_PASSWORD')} -e VHOST={environ.get('RABBIT_VHOST')} -e QUEUE_NAME={queue_name}" \
                 f" -e LOKI_HOST={GALLOPER_URL.replace('https://', 'http://')} " \
                 f"getcarrier/interceptor:{CONTAINER_TAG}"
    return user_data
