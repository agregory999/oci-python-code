import io
import random
import string
import json
import logging
import oracledb
import oci
from zipfile import ZipFile

from fdk import response

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)
logging.getLogger('oci._vendor.urllib3.connectionpool').setLevel(logging.INFO)
logger.setLevel(logging.INFO)

# Code from OCI Functions Samples
def get_dbwallet_from_autonomousdb(adb_ocid) -> tuple:
    '''Return a tuple of location and wallet password'''
    dbwallet_location = "/tmp"
    dbwalletzip_location = f"{dbwallet_location}/Wallet.zip"

    logger.info(f"Getting ADB Wallet for ocid: {adb_ocid}")
    signer = oci.auth.signers.get_resource_principals_signer()   # authentication based on instance principal
    atp_client = oci.database.DatabaseClient(config={}, signer=signer)
    atp_wallet_pwd = ''.join(random.choices(string.ascii_uppercase + string.digits, k=15)) # random string
    # the wallet password is only used for creation of the Java jks files, which aren't used by cx_Oracle so the value is not important
    atp_wallet_details = oci.database.models.GenerateAutonomousDatabaseWalletDetails(password=atp_wallet_pwd)
    logger.debug(atp_wallet_details)
    obj = atp_client.generate_autonomous_database_wallet(adb_ocid, atp_wallet_details)
    logger.info(f"Wallet downloaded: {obj}")
    
    # Download wallet to /tmp
    with open(dbwalletzip_location, 'w+b') as f:
        for chunk in obj.data.raw.stream(1024 * 1024, decode_content=False):
            f.write(chunk)
    with ZipFile(dbwalletzip_location, 'r') as zipObj:
            zipObj.extractall(dbwallet_location)
    
    logger.info(f"Wallet downloaded and extracted to {dbwalletzip_location}")

    # Whatever should be referenced in the connection
    return (dbwallet_location, atp_wallet_pwd)

def connect(user: str, password: str, dsn: str, wallet: tuple) -> oracledb.Connection:
    '''Require connection info'''
    logger.info(f"Connecting to DB: {dsn}")
    try:
        oracledb.init_oracle_client()
    except Exception as ex:
        logger.warn(f"Failed to set up Thick Driver, reverting to thin: {ex}")
        
    connection = oracledb.connect(
        user=user,
        password=password,
        dsn=dsn,
        wallet_location=wallet[0],
        wallet_password=wallet[1]
    )
    logger.info("Connected to Oracle")
    return connection

def handler(ctx, data: io.BytesIO = None):

    # Get Event from Body and process it
    try:
        # Get Configuration from Function (see console)
        cfg = dict(ctx.Config())
        json_collection = cfg["JSON_COLLECTION"]
        adb_ocid = cfg["ADB_OCID"]
        adb_user = cfg["ADB_USER"]
        adb_pass = cfg["ADB_PASS"]
        adb_dsn = cfg["ADB_DSN"]
        
        logger.info(f"Using DB: {adb_ocid}")

        body = json.loads(data.getvalue())

        # Generate Wallet
        wallet = get_dbwallet_from_autonomousdb(adb_ocid)
        logger.info(f"Wallet Location: {wallet[0]} Pass: {wallet[1]}")

        # Connect to ADB JSON instance
        connection = connect(user=adb_user,
                             password=adb_pass,
                             dsn=adb_dsn,
                             wallet=wallet)

        # Perform Insert
        with connection.cursor() as cursor:
            data = body
            logger.info(f"Body: {body}")

            # Query
            insert_sql = f"insert into {json_collection} values (:1)"

            # Cursor
            cursor.setinputsizes(oracledb.DB_TYPE_JSON)

            logger.info(f"Executing SQL: {insert_sql}")
            
            # Execute
            cursor.execute(insert_sql, [data])

            logger.debug(f"Executed SQL")

            connection.commit()

            logger.info(f"Completed Insert Commit")
    except (Exception, ValueError) as ex:
        logger.error(f"Error: {ex}")

