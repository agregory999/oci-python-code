#!/usr/bin/env python3
import threading, time
import traceback
import os
import json
import logging

from kafka import KafkaConsumer

# Logging
logging.basicConfig(level=logging.DEBUG)

# Basics
stream_name = os.environ.get('STREAM_NAME', 'stream')
endpoint = os.environ.get('KAFKA_HOST', 'streaming.us-ashburn-1.oci.oraclecloud.com:9092')
print(f"Endpoint: {endpoint} | Stream: {stream_name}",flush=True)

try: 
    consumer = KafkaConsumer(stream_name,bootstrap_servers=endpoint,
                        security_protocol=os.environ.get('KAFKA_PROT', 'SASL_SSL'),
                        sasl_mechanism='PLAIN',
                        #sasl_plain_username='orasenatdpltintegration01/oracleidentitycloudservice/andrew.gregory@oracle.com/ocid1.streampool.oc1.iad.amaaaaaaytsgwayaqu64fqjs32sna5dwxwcqvgnpv3py6y4nvp4yomen26nq',
                        #sasl_plain_username='windstreamoci/QRadar_Stream_Usr/ocid1.streampool.oc1.iad.amaaaaaahwcsg7aatq6enm6eob5kpnifcpyelsaolzcgygmrfruyszde3jna',
                        sasl_plain_username='windstreamoci/N9889247/ocid1.streampool.oc1.iad.amaaaaaahwcsg7aatq6enm6eob5kpnifcpyelsaolzcgygmrfruyszde3jna',
                        #sasl_plain_password='Mg0<:m:0PY7t#>R4B3Td',  #integration01
                        #sasl_plain_password='R7cAt4ZgnL+DQMummA_{',  #WS qradar user token 1
                        #sasl_plain_password='9Fa8A{nj]5bt7qtIF{.l',  #WS qradar user token 2
                        sasl_plain_password='p50YoGNihn{y8T.{3l78',  # WS AG
                        auto_offset_reset='earliest',
                        #consumer_timeout_ms=1000,
                        request_timeout_ms=60000,
                        api_version=(0,10),
                        #api_version=None,
                        #api_version_auto_timeout_ms=1000,
                        group_id='group-0',
                        value_deserializer=json.loads
                        )
    
    # Poll method
    #messages = consumer.poll(max_records=5)
    #print(f'Got {len(messages)} Messages')

    # Iterator Method
    for message in consumer:
        #print(f'Message: {message}')
        if message.value["data"]["identity"]["authType"] == "fed":
            print(f'User: {message.value["data"]["identity"]["principalName"]} \
/ {message.value["data"]["identity"]["userAgent"]} / {message.value["data"]["request"]["path"]}', flush=True)
        else:
            print(f'System: {message.value["data"]["identity"]["principalName"]} \ {message.value["data"]["request"]["path"]}', flush=True)

    # Close
    consumer.close()
except Exception as e:
    print(f'Exception: {traceback.format_exc()}')
    exit(1)
