import oracledb
import json

ADMIN_PWD = "WW33lcome1#####"
WALLET_PWD = "4KidsH0nda@@@"

# Connect to Oracle Autonomous Database using the wallet
connection=oracledb.connect(
     config_dir="/Users/agregory/oci-python-code/oracle-db",
     user="admin",
     password=ADMIN_PWD,
     dsn="agatp23ai_low",
     wallet_location="/Users/agregory/oci-python-code/oracle-db",
     wallet_password=WALLET_PWD)

print(f"Successfully connected to Oracle Autonomous Database: {connection.version}")

# Create a temporary table and insert sample data
cursor = connection.cursor()
cursor.execute("CREATE TABLE temp_table (id NUMBER, name VARCHAR2(50))")
cursor.execute("INSERT INTO temp_table (id, name) VALUES (1, 'Sample Name')")
connection.commit() 

# List all tables in the user's schema
cursor.execute("SELECT table_name FROM user_tables")
tables = cursor.fetchall()
print("Tables in the schema:")
for table in tables:
    print(table[0])

# Create a JSON and query data using regular SQL then put into my JSON object
cursor.execute("SELECT id, name FROM temp_table")
rows = cursor.fetchall()
data = [{"id": row[0], "name": row[1]} for row in rows]
json_data = json.dumps(data, indent=4)
print("Data in JSON format:")
print(json_data)
# Clean up
cursor.execute("DROP TABLE temp_table")
cursor.close()
connection.close()