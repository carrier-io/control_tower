from time import sleep
from typing import Callable

from arbiter import Arbiter

from control_tower.constants import RABBIT_HOST, RABBIT_PORT, RABBIT_USER, RABBIT_PASSWORD, \
    RABBIT_VHOST, GALLOPER_URL
from control_tower.run import logger


def get_instances_requirements(args, cloud_config, queue_name):
    instance_count = 0
    cpu = max(2, int(cloud_config["cpu_cores_limit"]))
    memory = int(cloud_config["memory_limit"]) + 1
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
    return cpu, instance_count, memory


def wait_for_instances_start(args, instance_count: int, terminate_instance_func: Callable):
    arbiter = Arbiter(host=RABBIT_HOST, port=RABBIT_PORT, user=RABBIT_USER,
                      password=RABBIT_PASSWORD, vhost=RABBIT_VHOST)
    retry = 5
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
                logger.info("Instances set up timeout - 600 seconds ...")
                terminate_instance_func()
                raise Exception("Couldn't set up cloud instances")


def get_instance_init_script(args, cpu, finalizer_queue_name, memory, queue_name):
    user_data = '''#!/bin/bash
    
    apt update -y
    apt install docker -y
    apt install docker.io -y
    '''
    user_data += f"docker pull {args.container[0]}\n"
    user_data += f"docker run -d -v /var/run/docker.sock:/var/run/docker.sock -e RAM_QUOTA=1g -e CPU_QUOTA=1" \
                 f" -e CPU_CORES=1 -e RABBIT_HOST={RABBIT_HOST} -e RABBIT_USER={RABBIT_USER}" \
                 f" -e RABBIT_PASSWORD={RABBIT_PASSWORD} -e VHOST={RABBIT_VHOST} -e QUEUE_NAME={finalizer_queue_name}" \
                 f" -e LOKI_HOST={GALLOPER_URL.replace('https://', 'http://')} " \
                 f"getcarrier/interceptor:latest\n"
    user_data += f"docker run -d -v /var/run/docker.sock:/var/run/docker.sock -e RAM_QUOTA={memory}g -e CPU_QUOTA={cpu * 0.9}" \
                 f" -e CPU_CORES=1 -e RABBIT_HOST={RABBIT_HOST} -e RABBIT_USER={RABBIT_USER}" \
                 f" -e RABBIT_PASSWORD={RABBIT_PASSWORD} -e VHOST={RABBIT_VHOST} -e QUEUE_NAME={queue_name}" \
                 f" -e LOKI_HOST={GALLOPER_URL.replace('https://', 'http://')} " \
                 f"getcarrier/interceptor:latest"
    return user_data
