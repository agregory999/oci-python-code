from langchain_community.llms import OCIGenAI

llm = OCIGenAI(
    model_id="cohere.command",
    #model_id="meta.llama-2-70b-chat",
    service_endpoint="https://inference.generativeai.us-chicago-1.oci.oraclecloud.com",
    compartment_id="ocid1.compartment.oc1..aaaaaaaa6hti46iwez3xa2bikcfkeqzqiqdzxtujagmsacng7luxultxtkza", # replace with your OCID
    #auth_profile="INTEGRATION"
    model_kwargs={"temperature": 4.0, "max_tokens": 500}
)

response = llm.invoke("Is Snowflake expensive?")
print(f"Resp: {response}", flush=True)
