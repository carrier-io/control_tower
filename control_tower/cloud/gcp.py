import json
from typing import Any, List
from uuid import uuid4

import arbiter
from google.api_core.extended_operation import ExtendedOperation
from google.cloud import compute_v1
from google.cloud.compute_v1.types import Image
from google.oauth2.service_account import Credentials

from control_tower.cloud.common import get_instances_requirements, get_instance_init_script, \
    wait_for_instances_start
from control_tower.run import logger


def wait_for_extended_operation(
        operation: ExtendedOperation, verbose_name: str = "operation", timeout: int = 300
) -> Any:
    """
    This method will wait for the extended (long-running) operation to
    complete. If the operation is successful, it will return its result.
    If the operation ends with an error, an exception will be raised.
    If there were any warnings during the execution of the operation
    they will be printed to sys.stderr.

    Args:
        operation: a long-running operation you want to wait on.
        verbose_name: (optional) a more verbose name of the operation,
            used only during error and warning reporting.
        timeout: how long (in seconds) to wait for operation to finish.
            If None, wait indefinitely.

    Returns:
        Whatever the operation.result() returns.

    Raises:
        This method will raise the exception received from `operation.exception()`
        or RuntimeError if there is no exception set, but there is an `error_code`
        set for the `operation`.

        In case of an operation taking longer than `timeout` seconds to complete,
        a `concurrent.futures.TimeoutError` will be raised.
    """
    result = operation.result(timeout=timeout)

    if operation.error_code:
        logger.error(
            f"Error during {verbose_name}: "
            f"[Code: {operation.error_code}]: {operation.error_message}")
        logger.error(f"Operation ID: {operation.name}")
        raise operation.exception() or RuntimeError(operation.error_message)

    if operation.warnings:
        logger.warning(f"Warnings during {verbose_name}:\n")
        for warning in operation.warnings:
            logger.warning(f" - {warning.code}: {warning.message}")

    return result


def get_ubuntu_image(credentials: Credentials) -> Image:
    image_client = compute_v1.ImagesClient(credentials=credentials)
    newest_image = image_client.get_from_family(project="ubuntu-os-cloud",
                                                family="ubuntu-2204-lts")
    return newest_image


def get_machine_type(cpu, memory):
    memory_in_mb = memory << 10
    cpu = cpu if cpu % 2 == 0 else cpu + 1
    return f"custom-{cpu}-{memory_in_mb}"


def create_instance(
        credentials: Credentials, name: str, spot: bool, user_data: str, project: str,
        zone: str, machine_type: str
) -> ExtendedOperation:
    instance_client = compute_v1.InstancesClient(credentials=credentials)
    instance = compute_v1.Instance(
        name=name,
        machine_type=f'zones/{zone}/machineTypes/{machine_type}',
        disks=[compute_v1.AttachedDisk(
            architecture="X86_64",
            auto_delete=True,
            boot=True,
            disk_size_gb=10,
            initialize_params={
                "source_image": get_ubuntu_image(credentials).self_link
            }
        )],
        metadata={
            "items": [
                {'key': 'startup-script', 'value': user_data}]
        }
    )
    network_interface = compute_v1.NetworkInterface()
    access = compute_v1.AccessConfig()
    access.type_ = compute_v1.AccessConfig.Type.ONE_TO_ONE_NAT.name
    access.name = "External NAT"
    network_interface.access_configs = [access]
    instance.network_interfaces = [network_interface]
    if spot:
        instance.scheduling = compute_v1.Scheduling()
        instance.scheduling.provisioning_model = (
            compute_v1.Scheduling.ProvisioningModel.SPOT.name
        )
        instance.scheduling.instance_termination_action = "DELETE"

    return instance_client.insert(project=project,
                                  zone=zone,
                                  instance_resource=instance)


def create_gcp_instances(args, gcp_settings):
    logger.info("Requesting GCP Instances...")
    queue_name = str(uuid4())
    finalizer_queue_name = str(uuid4())

    cpu, instance_count, memory = get_instances_requirements(args, gcp_settings, queue_name)
    machine_type = get_machine_type(cpu, memory)
    user_data = get_instance_init_script(args, cpu, finalizer_queue_name, memory, queue_name, instance_count)
    service_account_info = json.loads(gcp_settings["service_account_info"])
    credentials = Credentials.from_service_account_info(service_account_info)

    instance_names = [f"test-{i + 1}-{queue_name[:8]}" for i in range(instance_count)]
    operations = [
        create_instance(
            credentials=credentials,
            name=instance_name,
            spot=gcp_settings["instance_type"] == "spot",
            user_data=user_data,
            project=gcp_settings["project"],
            zone=gcp_settings["zone"],
            machine_type=machine_type
        )
        for instance_name in instance_names
    ]
    for instance, operation in zip(instance_names, operations):
        wait_for_extended_operation(operation, f"instance {instance} creation")
        logger.info(f"Instance {instance} created.")

    wait_for_instances_start(
        args, instance_count,
        lambda: terminate_instances(credentials, gcp_settings["project"],
                                    gcp_settings["zone"], instance_names)
    )
    terminate_task_kwargs = {
        "service_account_info": service_account_info,
        "project": gcp_settings["project"],
        "zone": gcp_settings["zone"],
        "instances": instance_names
    }

    finalizer_task = arbiter.Task("terminate_gcp_instances", queue=finalizer_queue_name,
                                  task_type="finalize", task_kwargs=terminate_task_kwargs)
    return finalizer_task


def terminate_instances(
        credentials: Credentials, project: str, zone: str, instances: List[str]
):
    instance_client = compute_v1.InstancesClient(credentials=credentials)
    operations = [
        instance_client.delete(
            project=project,
            zone=zone,
            instance=instance_name
        ) for instance_name in instances
    ]
    for instance, operation in zip(instances, operations):
        wait_for_extended_operation(operation, f"instance {instance} termination")
        logger.info(f"Instance {instance} terminated.")
