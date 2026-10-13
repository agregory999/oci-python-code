# coding: utf-8
# Copyright (c) 2023, Oracle and/or its affiliates.  All rights reserved.
# This software is dual-licensed to you under the Universal Permissive License (UPL) 1.0 as shown at https://oss.oracle.com/licenses/upl or Apache License 2.0 as shown at http://www.apache.org/licenses/LICENSE-2.0. You may choose either license.

##########################################################################
# generate_text_demo.py
# Supports Python 3
##########################################################################
# Info:
# Get texts from LLM model for given prompts using OCI Generative AI Service.
##########################################################################
# Application Command line(no parameter needed)
# python generate_text_demo.py
##########################################################################
import oci

# Setup basic variables
# Auth Config
# TODO: Please update config profile name and use the compartmentId that has policies grant permissions for using Generative AI Service
compartment_id = "ocid1.compartment.oc1..aaaaaaaatjhyragop24gi7wqh73f53uo6qntbhke67a4tbgm3shrljbi54mq"
CONFIG_PROFILE = "INTEGRATION-ADMIN-ORD"
config = oci.config.from_file('~/.oci/config', CONFIG_PROFILE)

# Service endpoint
endpoint = "https://inference.generativeai.us-chicago-1.oci.oraclecloud.com"

generative_ai_inference_client = oci.generative_ai_inference.GenerativeAiInferenceClient(config=config, service_endpoint=endpoint, retry_strategy=oci.retry.NoneRetryStrategy(), timeout=(10,240))
generate_text_detail = oci.generative_ai_inference.models.GenerateTextDetails()

# Llama vs Cohere Command Light

#llm_inference_request = oci.generative_ai_inference.models.LlamaLlmInferenceRequest()
llm_inference_request = oci.generative_ai_inference.models.CohereLlmInferenceRequest()
llm_inference_request.prompt = "Generate a product pitch for Oracle Generative AI and Retrieval Augmented Generation within OCI."

llm_inference_request.max_tokens = 600

# Llama vs Cohere Command Light

#llm_inference_request.temperature = 0.5
llm_inference_request.temperature = 1
#llm_inference_request.frequency_penalty = 1
llm_inference_request.frequency_penalty = 0

llm_inference_request.top_p = 0.75

# Llama vs Cohere Command Light
#generate_text_detail.serving_mode = oci.generative_ai_inference.models.OnDemandServingMode(model_id="ocid1.generativeaimodel.oc1.us-chicago-1.amaaaaaask7dceyai3pxxkeezogygojnayizqu3bgslgcn6yiqvmyu3w75ma")
generate_text_detail.serving_mode = oci.generative_ai_inference.models.OnDemandServingMode(model_id="ocid1.generativeaimodel.oc1.us-chicago-1.amaaaaaask7dceyad4uybcjtw475o4uqja3oz3kzrfhln7joysjxj3npp2la")

generate_text_detail.inference_request = llm_inference_request
generate_text_detail.compartment_id = compartment_id
generate_text_response = generative_ai_inference_client.generate_text(generate_text_detail)
# Print result
print("**************************Generate Texts Result**************************")
print(generate_text_response.data)
