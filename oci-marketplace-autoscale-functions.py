# Copyright (c) 2019, 2022, Oracle and/or its affiliates. All rights reserved.
#


import os
import json
import subprocess
import sys
import time
import oci
import urllib.request
import traceback
from io import open

VOLUME_MOUNTED_MARKER = '/u01/.volumeMountedMarker'

def get_custom_retry_strategy():
    """
    Builds a custom retry strategy to be used with python SDK APIs.
    By default, operations exposed in the SDK do not retry.
    Custom retry was needed to add 404 error code for retry which is not
    included with the DEFAULT_RETRY_STRATEGY.
    See https://docs.oracle.com/en-us/iaas/tools/python/2.54.1/sdk_behaviors/retries.html

    :return:
    """
    # Define a custom strategy
    return oci.retry.RetryStrategyBuilder(
        # Make up to 30 service calls
        max_attempts_check=True,
        max_attempts=30,

        # Don't exceed a total of 1200 seconds for all service calls
        total_elapsed_time_check=True,
        total_elapsed_time_seconds=1200, # 20 mins

        # Wait 45 seconds between attempts
        retry_max_wait_between_calls_seconds=45,

        # Use 2 seconds as the base number for doing sleep time calculations
        retry_base_sleep_time_seconds=2,

        # Retry on certain service errors:
        #
        #   - 5xx code received for the request
        #   - Any 429 (this is signified by the empty array in the retry config)
        #   - 400s where the code is QuotaExceeded or LimitExceeded
        service_error_check=True,
        service_error_retry_on_any_5xx=True,
        service_error_retry_config={
            400: ['QuotaExceeded', 'LimitExceeded'],
            429: [],
            404: []
        },

        # Use exponential backoff and retry with full jitter, but on throttles use
        # exponential backoff and retry with equal jitter
        backoff_type=oci.retry.BACKOFF_FULL_JITTER_EQUAL_ON_THROTTLE_VALUE
    ).get_retry_strategy()


def log(msg):
    print(msg, flush=True)
def get_instance_attribute(attribute, dvalue=None):
    """
    Returns instance attribute or default value if no value is found
    """
    try:
        request_headers = {
            "Authorization": "Bearer Oracle"
        }
        request = urllib.request.Request("http://169.254.169.254/opc/v2/instance/" + attribute,
                                  headers=request_headers)
        result = urllib.request.urlopen(request).read()
        return result.decode('utf-8')
    except:
        pass

    try:
        result = urllib.request.urlopen('http://169.254.169.254/opc/v1/instance/' + attribute).read()
        return result.decode('utf-8')
    except:
        pass

def get_metadata_attribute(attribute, default=None):
    """
    Returns attribute or default value if no value is found
    """
    try:
        request_headers = {
            "Authorization": "Bearer Oracle"
        }
        request = urllib.request.Request("http://169.254.169.254/opc/v2/instance/metadata/" + attribute,
                                  headers=request_headers)
        result = urllib.request.urlopen(request).read()
        return result.decode('utf-8')
    except:
        pass

    try:
        result = urllib.request.urlopen('http://169.254.169.254/opc/v1/instance/metadata/' + attribute).read()
        return result.decode('utf-8')
    except:
        pass

    return default

def create_marker_file(marker_file, msg=None, on_success=None, is_timedout=None):
    """
    With MW volume creation, the volume mount scripts are moved to the wls image, this
    code is duplicated from markers so we can create volumeMount marker.

    :param marker_file:
    :param msg: In the marker file we can put message to be logged during status check.
    :return:
    """
    if not os.path.exists(os.path.dirname(marker_file)):
        os.makedirs(os.path.dirname(marker_file))
    file = None
    try:
        file= open(marker_file,"w+")

        if msg is not None:
            if on_success is not None and on_success:
                msg_prefix = "WLS-0001" + "-SUCCESS"
            elif on_success is not None and not on_success:
                msg_prefix = "WLS-0001" + "-FAILED"
            file.write(msg_prefix + " : " + msg)
        if file is not None:
            file.close()
    except:
        raise


def execute(command):
    """
    Executes a shell command.
    :param command:
    :return:
    """
    log("executing: {0}".format(command))
    exit_status = None
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        out, err = process.communicate()
        exit_status = process.returncode
    except:
        e = sys.exc_info()[0]
        log(e)
        log(err)
    return out, exit_status


def list_volume(block_storage, compartment_id, availability_domain, display_name):
    result = block_storage.list_volumes(
        compartment_id=compartment_id,
        availability_domain=availability_domain,
        lifecycle_state='AVAILABLE',
        display_name=display_name,
        retry_strategy=get_custom_retry_strategy()
    )
    return result

def wait_for_resource_in_state(compute_client, compartment_id, instance_ocid, volume_id, display_name):
    max_retries = 30
    sleep_interval = 5
    retry_count = max_retries
    attachment = ()
    while retry_count >0:
        iscsi_volume_attachment = compute_client.list_volume_attachments(
            compartment_id=compartment_id,
            instance_id=instance_ocid,
            volume_id=volume_id,
            retry_strategy=get_custom_retry_strategy()
        )
        if len(iscsi_volume_attachment.data) != 1:
            log("Waiting for volume attachment creation to complete ... : [%s]" % display_name)
            time.sleep(sleep_interval)
            retry_count -= 1
        else:
            if iscsi_volume_attachment.data[0].lifecycle_state == "ATTACHED":
                log("Got volume attachment info: [%s]" % (display_name))
                attachment = iscsi_volume_attachment.data[0]
                break
            else:
                log("Polling for volume attachment info required for iscsiadm setup : [%s]" % display_name)
                time.sleep(sleep_interval)
                retry_count -= 1

    return attachment

def get_volume_attachments():
    attachments = []
    try:
        """
        The below call for InstancePrincipalsSecurityTokenSigner() fails intermittently in some tenancies when trying
        to retrieve the certificate for the instance principal signer from auth endpoint in the region.
        Adding custom retry so we wait for the IMDS auth endpoint for the region to become available during instance
        bootstrap.
        """
        custom_retry_strategy = get_custom_retry_strategy()
        principal = oci.auth.signers.InstancePrincipalsSecurityTokenSigner(retry_strategy = custom_retry_strategy)
        principal = oci.auth.signers.InstancePrincipalsSecurityTokenSigner(retry_strategy = custom_retry_strategy)
        compute_client = oci.core.ComputeClient(config={}, signer=principal)
        block_storage_client = oci.core.BlockstorageClient(config={}, signer=principal)
        instance_ocid = get_instance_attribute("id")
        compartment_id = get_instance_attribute("compartmentId")
        availability_domain = get_instance_attribute("availabilityDomain")
        for i in range(0, 2):
            if i == 0:
                display_name = get_metadata_attribute("service_name") + '-mw' + '-block-' + str(get_metadata_attribute("host_index"))
            else:
                display_name = get_metadata_attribute("service_name") + '-data' + '-block-' + str(get_metadata_attribute("host_index"))

            volume = list_volume(block_storage_client, compartment_id, availability_domain, display_name.rstrip())

            if len(volume.data) !=1:
                msg = 'ERROR - Unable to retrieve volume attachment information due to multiple block volumes [AD={} , display_name={}]'.format(
                    availability_domain, display_name)
                log(msg)
                create_marker_file(VOLUME_MOUNTED_MARKER, msg, on_success=False)
                sys.exit(-1)

            attachments.append(wait_for_resource_in_state(compute_client, compartment_id, instance_ocid, volume.data[0].id, display_name))
    except Exception as e:
        msg_stack = traceback.format_exc()
        log(msg_stack)
        log("Exception stacktrace [{}]".format(str(e)))
        msg = 'ERROR - Unable to retrieve volume attachment information : [{}]'.format(str(e))
        create_marker_file(VOLUME_MOUNTED_MARKER, msg, on_success=False)
        sys.exit(-1)

    return attachments

def mount_domain_volume():
    log("Configuring and mounting middleware and data volumes")
    data = get_volume_attachments()
    if len(data) == 2 and data[0] and data[1]:
        for i in range(len(data)):
            if i == 0:
                mount_point = get_metadata_attribute("mw_vol_mount_point")
                device = get_metadata_attribute("mw_vol_device")
            else:
                mount_point = get_metadata_attribute("data_vol_mount_point")
                device = get_metadata_attribute("data_vol_device")

            log_file = get_metadata_attribute("logs_dir") + "/bootstrap.log"
            log("Mount Point: [%s], device: [%s]" % (mount_point, device))
            out, exit_code = execute(
                '/opt/scripts/attachNmountVolume.sh {0} {1} {2} {3} {4} {5}'.format(mount_point, device, data[i].iqn,
                                                                                    data[i].port, data[i].ipv4, log_file))
            if exit_code != 0:
                msg = 'ERROR - Could not mount the volume [{0}]. Check the vm logs.'.format(str(exit_code))
                log(msg)
                create_marker_file(VOLUME_MOUNTED_MARKER, msg, on_success=False)
                sys.exit(-1)
            else:
                msg = "Completed mounting volume at [%s]" % (mount_point)
                create_marker_file(VOLUME_MOUNTED_MARKER, msg, on_success=True)
    else:
        msg = 'ERROR - Volume information is not available. Cannot attach or mount the volume.'
        log(msg)
        create_marker_file(VOLUME_MOUNTED_MARKER, msg, on_success=False)
        sys.exit(-1)


if __name__ == '__main__':
    mount_domain_volume()