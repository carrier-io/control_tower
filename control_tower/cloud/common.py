from time import sleep
from typing import Callable
from os import environ

import ssl
from arbiter import Arbiter, EventNode, RedisEventNode, SocketIOEventNode

from control_tower.constants import RABBIT_HOST, RABBIT_PORT, RABBIT_USER, RABBIT_PASSWORD, \
    RABBIT_VHOST, GALLOPER_URL, CONTAINER_TAG, RABBIT_USE_SSL, RABBIT_SSL_VERIFY
from control_tower.run import logger


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
        event_node_runtime = environ.get("ARBITER_RUNTIME", "rabbitmq")
        #
        if event_node_runtime == "rabbitmq":
            node_config = {
                "use_ssl": environ.get("RABBIT_USE_SSL", "").lower() in ["true", "yes"],
                "ssl_verify": environ.get("RABBIT_SSL_VERIFY", "").lower() in ["true", "yes"],
                "host": environ.get("RABBIT_HOST"),
                "port": int(environ.get("RABBIT_PORT", "5672")),
                "user": environ.get("RABBIT_USER"),
                "password": environ.get("RABBIT_PASSWORD"),
                "vhost": environ.get("RABBIT_VHOST"),
                "queue": "tasks",
                "hmac_key": None,
                "hmac_digest": "sha512",
                "callback_workers": int(environ.get("EVENT_NODE_WORKERS", "1")),
                "mute_first_failed_connections": 10,
            }
            #
            ssl_context=None
            ssl_server_hostname=None
            #
            if node_config.get("use_ssl", False):
                ssl_context = ssl.create_default_context()
                if node_config.get("ssl_verify", False) is True:
                    ssl_context.verify_mode = ssl.CERT_REQUIRED
                    ssl_context.check_hostname = True
                    ssl_context.load_default_certs()
                else:
                    ssl_context.check_hostname = False
                    ssl_context.verify_mode = ssl.CERT_NONE
                ssl_server_hostname = node_config.get("host")
            #
            event_node = EventNode(
                host=node_config.get("host"),
                port=node_config.get("port", 5672),
                user=node_config.get("user", ""),
                password=node_config.get("password", ""),
                vhost=node_config.get("vhost", "carrier"),
                event_queue=node_config.get("queue", "rpc"),
                hmac_key=node_config.get("hmac_key", None),
                hmac_digest=node_config.get("hmac_digest", "sha512"),
                callback_workers=node_config.get("callback_workers", 1),
                ssl_context=ssl_context,
                ssl_server_hostname=ssl_server_hostname,
                mute_first_failed_connections=node_config.get("mute_first_failed_connections", 10),  # pylint: disable=C0301
            )
        elif event_node_runtime == "redis":
            node_config = {
                "host": environ.get("REDIS_HOST"),
                "port": int(environ.get("REDIS_PORT", "6379")),
                "password": environ.get("REDIS_PASSWORD"),
                "queue": environ.get("REDIS_VHOST"),
                "hmac_key": None,
                "hmac_digest": "sha512",
                "callback_workers": int(environ.get("EVENT_NODE_WORKERS", "1")),
                "mute_first_failed_connections": 10,
                "use_ssl": environ.get("REDIS_USE_SSL", "").lower() in ["true", "yes"],
            }
            #
            event_node = RedisEventNode(
                host=node_config.get("host"),
                port=node_config.get("port", 6379),
                password=node_config.get("password", ""),
                event_queue=node_config.get("queue", "events"),
                hmac_key=node_config.get("hmac_key", None),
                hmac_digest=node_config.get("hmac_digest", "sha512"),
                callback_workers=node_config.get("callback_workers", 1),
                mute_first_failed_connections=node_config.get("mute_first_failed_connections", 10),  # pylint: disable=C0301
                use_ssl=node_config.get("use_ssl", False),
            )
        elif event_node_runtime == "socketio":
            node_config = {
                "url": environ.get("SIO_URL"),
                "password": environ.get("SIO_PASSWORD"),
                "room": environ.get("SIO_VHOST"),
                "hmac_key": None,
                "hmac_digest": "sha512",
                "callback_workers": int(environ.get("EVENT_NODE_WORKERS", "1")),
                "mute_first_failed_connections": 10,
                "ssl_verify": environ.get("SIO_SSL_VERIFY", "").lower() in ["true", "yes"],
            }
            #
            event_node = SocketIOEventNode(
                url=node_config.get("url"),
                password=node_config.get("password", ""),
                room=node_config.get("room", "events"),
                hmac_key=node_config.get("hmac_key", None),
                hmac_digest=node_config.get("hmac_digest", "sha512"),
                callback_workers=node_config.get("callback_workers", 1),
                mute_first_failed_connections=node_config.get("mute_first_failed_connections", 10),  # pylint: disable=C0301
                ssl_verify=node_config.get("ssl_verify", False),
            )
        else:
            raise ValueError(f"Unsupported arbiter runtime: {event_node_runtime}")
        #
        arbiter = Arbiter(event_node=event_node)
    except:
        terminate_instance_func()
        raise Exception("Couldn't connect to Arbiter")
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


def get_instance_init_script(args, cpu, finalizer_queue_name, memory, queue_name, instance_count=None):
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
    user_data += f"docker pull {args.container[0]}\n"
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
