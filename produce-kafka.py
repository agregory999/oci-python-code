#!/usr/bin/env python3
import threading, time
import logging
import traceback
import os
import json

from kafka import KafkaProducer
from kafka.admin import NewTopic

# Logging
logging.basicConfig(level=logging.DEBUG)

print(f"Consumer using host: {os.environ.get('KAFKA_HOST', 'streaming.us-ashburn-1.oci.oraclecloud.com:9092')}",flush=True)
try: 
    stream_name = 'test'
    producer = KafkaProducer(bootstrap_servers=os.environ.get('KAFKA_HOST', 'streaming.us-ashburn-1.oci.oraclecloud.com:9092'),
                                security_protocol=os.environ.get('KAFKA_PROT', 'SASL_SSL'),
                                sasl_mechanism='PLAIN',
                                sasl_plain_username='orasenatdpltintegration01/oracleidentitycloudservice/andrew.gregory@oracle.com/ocid1.streampool.oc1.iad.amaaaaaaytsgwayaqu64fqjs32sna5dwxwcqvgnpv3py6y4nvp4yomen26nq',
                                #sasl_plain_username='windstreamoci/QRadar_Stream_Usr/ocid1.streampool.oc1.iad.amaaaaaahwcsg7aatq6enm6eob5kpnifcpyelsaolzcgygmrfruyszde3jna',
                                #sasl_plain_username='windstreamoci/N9889247/ocid1.streampool.oc1.iad.amaaaaaahwcsg7aatq6enm6eob5kpnifcpyelsaolzcgygmrfruyszde3jna',
                                sasl_plain_password='Mg0<:m:0PY7t#>R4B3Td',  #integration01
                                #sasl_plain_password='R7cAt4ZgnL+DQMummA_{',  #WS qradar user token 1
                                #sasl_plain_password='9Fa8A{nj]5bt7qtIF{.l',  #WS qradar user token 2
                                #sasl_plain_password='9(gc[uy<q]m0hT#O)4U)',
                                #request_timeout_ms=2000,
                                #api_version=(0,10,1),
                                linger_ms=0,
                                #api_version=None,
                                #api_version_auto_timeout_ms=1000,
                                #value_serializer=json.dumps
                                )
    #print(f'Producer: {producer.bootstrap_connected()}', flush=True)

    # Put a message
    json_data = {
        "president": {
            "name": "Zaphod Beeblebrox",
            "species": "Betelgeusian"
        }
    }
    producer.send(topic='prducer-test2', key=b'a',value=b'd')
    producer.flush()
    producer.close()

except Exception as e:
    print(f'Exception: {traceback.format_exc()}')
    exit(1)

