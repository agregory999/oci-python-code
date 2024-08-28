import getpass
import oracledb

#pw = getpass.getpass("Enter password: ")

connection = oracledb.connect(
    user="ANDREW",
    password="WW33lcome1#####",
    dsn="(description=(retry_count=20)(retry_delay=3)(address=(protocol=tcps)(port=1522)(host=adb.us-phoenix-1.oraclecloud.com))(connect_data=(service_name=oryuv5cto3rlato_agjson_medium.adb.oraclecloud.com))(security=(ssl_server_dn_match=yes)))",  # the connection string copied from the cloud console
    wallet_location="/Users/agregory/oci-python-code/oci-functions/oci-json-events/Wallet_AGJSON",
    wallet_password="WW33lcome1#####"
)

print("Successfully connected to Oracle Database")


# SODA

# # Create SODA database instance
# soda = connection.getSodaDatabase()
# # Create a new collection (if it doesn't exist)
# collection = soda.createCollection("Events")


# Create a table
with connection.cursor() as cursor:

    # Json data
    data = dict(name="Sally", dept="Sales", location="France")

    # Query
    insert_sql = "insert into events values (:1)"

    # Cursor
    cursor.setinputsizes(oracledb.DB_TYPE_JSON)

    # Execute
    cursor.execute(insert_sql, [data])

print(f"Query Executed: ")

connection.commit()
