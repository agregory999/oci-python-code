import io
import json
import logging

import oci.object_storage
import oci.ai_speech

logging.basicConfig(level=logging.INFO)
logging.getLogger('oci._vendor.urllib3.connectionpool').setLevel(logging.INFO)
logger = logging.getLogger(__name__)

def handler(ctx, data: io.BytesIO = None):
    try:
        # Get Configuration from Function (see console)
        cfg = dict(ctx.Config())
        output_bucket_name = cfg["output_bucket_name"]

        # Optional Debug
        if "debug" in cfg:
            logger.setLevel(logging.DEBUG)
            logger.debug("Set logging to debug")

        logger.debug(f"Inside Python function")
        body = json.loads(data.getvalue())
        
        # Grab Bucket and Object details
        bucket_name  = body["data"]["additionalDetails"]["bucketName"]
        object_name  = body["data"]["resourceName"]
        compartment_ocid = body["data"]["compartmentId"]

        # Create OCI Clients using Resource Principals
        signer = oci.auth.signers.get_resource_principals_signer()
        oss_client = oci.object_storage.ObjectStorageClient(config={}, signer=signer)
        speech_client = oci.ai_speech.AIServiceSpeechClient(config={}, signer=signer)
        oss_namespace = oss_client.get_namespace().data
        logger.info(f"Object NS / bucket / obj: {oss_namespace} / {bucket_name} / {object_name}")
        
        # Create the speech job
        speech_job = speech_client.create_transcription_job(
            create_transcription_job_details=oci.ai_speech.models.CreateTranscriptionJobDetails(
                compartment_id=compartment_ocid,
                input_location=oci.ai_speech.models.ObjectListInlineInputLocation(
                            object_locations=[
                                oci.ai_speech.models.ObjectLocation(
                                    namespace_name=oss_namespace,
                                    bucket_name=bucket_name,
                                    object_names=[object_name])
                            ],
                            location_type=oci.ai_speech.models.ObjectListFileInputLocation.LOCATION_TYPE_OBJECT_LIST_INLINE_INPUT_LOCATION
                ),
                output_location=oci.ai_speech.models.OutputLocation(
                    namespace_name=oss_namespace,
                    bucket_name=output_bucket_name,
                    prefix="funct/"),
                # display_name="EXAMPLE-displayName-Value",
                description=f"Function-based job",
                # additional_transcription_formats=["SRT"],
                model_details=oci.ai_speech.models.TranscriptionModelDetails(
                    model_type="ORACLE",
                    domain="GENERIC",
                    language_code="en-US",
                    transcription_settings=oci.ai_speech.models.TranscriptionSettings(
                        diarization=oci.ai_speech.models.Diarization(
                            is_diarization_enabled=False,
                            # number_of_speakers=12
                            ))),
                normalization=oci.ai_speech.models.TranscriptionNormalization(
                    is_punctuation_enabled=True,
                    filters=[
                        oci.ai_speech.models.ProfanityTranscriptionFilter(
                            type="PROFANITY",
                            mode="TAG")]),
            ),                
        )

        # Print results (but async)
        transcription_job = speech_job.data
        logger.debug(f"Output: {transcription_job.id}")
    except KeyError as ex:
        logger.error(f"Config error: {ex}", flush=True)
    except (Exception, ValueError) as ex:
        logger.info('error parsing json payload: ' + str(ex))
        logger.error(f"error: {ex}", flush=True)
