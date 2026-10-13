# coding: utf-8
##########################################################################
# Copyright (c) 2023, Oracle and/or its affiliates.  All rights reserved.
# This software is dual-licensed to you under the Universal Permissive License (UPL) 1.0 
# as shown at https://oss.oracle.com/licenses/upl or Apache License 2.0 as shown at 
# https://www.apache.org/licenses/LICENSE-2.0. You may choose either license.
##########################################################################
# Reference Link: https://python.langchain.com/docs/integrations/llms/oci_generative_ai/
##########################################################################
# Install packages
# pip install -U oci==2.141.1 langchain_core==0.3.29 langchain-community==0.3.14
##########################################################################
from langchain_community.chat_models import ChatOCIGenAI
from langchain_core.messages import HumanMessage

# Setup basic variables
# Auth Config
# TODO: Please update config profile name and use the compartmentId that has policies grant permissions for using Generative AI Service
COMPARTMENT_ID = "ocid1.compartment.oc1..aaaaaaaazgn5vtlrndakdili7vvsvstsr5p3t7nsm56wummhuk4tb5rgrfda"
AUTH_TYPE = "API_KEY" # The authentication type to use, e.g., API_KEY (default), SECURITY_TOKEN, INSTANCE_PRINCIPAL, RESOURCE_PRINCIPAL.
CONFIG_PROFILE = "NACEOCI01"

prompt="what is the meaning of life?"

# Service endpoint
endpoint = "https://inference.generativeai.us-chicago-1.oci.oraclecloud.com"

# initialize interface
chat = ChatOCIGenAI(
  model_id="ocid1.generativeaimodel.oc1.us-chicago-1.amaaaaaask7dceyanrlpnq5ybfu5hnzarg7jomak3q6kyhkzjsl4qj24fyoq",
  service_endpoint=endpoint,
  compartment_id=COMPARTMENT_ID,
  provider="cohere",
  model_kwargs={
    "temperature": 1,
    "max_tokens": 600,
    "frequency_penalty": 0,
    "presence_penalty": 0,
    "top_p": 0.75,
    "top_k": 0,
    "seed": None
  },
  auth_type=AUTH_TYPE,
  auth_profile=CONFIG_PROFILE
)

messages = [
  HumanMessage(content=prompt),
]

response = chat.invoke(messages)
# Print result
print("**************************Chat Result**************************")
print(vars(response))
