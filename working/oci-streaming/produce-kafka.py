#!/usr/bin/env python3
import logging
import traceback
import os
import argparse

from kafka import KafkaProducer
from kafka.admin import NewTopic

# Logging
logging.basicConfig()
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Argument Parse
parser = argparse.ArgumentParser()
parser.add_argument("-v", "--verbose", help="increase output verbosity", action="store_true")
parser.add_argument("-p", "--streampool", help="Stream Pool OCID", required=True)
parser.add_argument("-u", "--username", help="OCI Username (not OCID)", required=True)
parser.add_argument("-a", "--authtoken", help="OCI User Auth Token value", required=True)
parser.add_argument("-t", "--tenancyname", help="Tenancy Name (not OCID)", required=True)
parser.add_argument("-s", "--stream", help="Stream Name (not OCID)", required=True)
parser.add_argument("-e", "--endpoint", help="Streaming Endpoint URL:Port", default="streaming.us-ashburn-1.oci.oraclecloud.com:9092")

args = parser.parse_args()
verbose = args.verbose
stream_pool = args.streampool
username = args.username
password = args.authtoken
tenancy_name = args.tenancyname
stream_name = args.stream
endpoint = args.endpoint

# Construct Username for streaming
streaming_username = f"{tenancy_name}/{username}/{stream_pool}"

# Basic Logging verbosity
if verbose:
    logger.setLevel(logging.DEBUG)

# Output some details
logger.info(f"Endpoint: {endpoint} | Stream: {stream_name}")
logger.debug(f"Username: {streaming_username} Password: {password}")
try: 
    producer = KafkaProducer(bootstrap_servers=endpoint,
                                security_protocol='SASL_SSL',
                                sasl_mechanism='PLAIN',
                                sasl_plain_username=streaming_username,
                                sasl_plain_password=password,  #integration01
                                #request_timeout_ms=2000,
                                #api_version=(0,10,1),
                                linger_ms=0,
                                #api_version=None,
                                #api_version_auto_timeout_ms=1000,
                                #value_serializer=json.dumps
                                )

    # Put a message
    json_data = {
        "president": {
            "name": "Zaphod Beeblebrox",
            "species": "Betelgeusian"
        }
    }
    producer.send(topic=stream_name, key=b'a',value=b'd')
    producer.flush()
    producer.close()

except Exception as e:
    print(f'Exception: {traceback.format_exc()}')
    exit(1)

