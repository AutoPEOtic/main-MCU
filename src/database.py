import pymysql

# Global variable to hold the database connection
connection = None

# Connect to the MySQL database.
def init(host, user, password, database, port=3306):
    global connection
    connection = pymysql.connect(
        host=host,
        user=user,
        password=password,
        database=database,
        port=port,
        cursorclass=pymysql.cursors.DictCursor,  # Results as dictionaries
        autocommit=True                          # Auto-commit changes
    )

def send(query):
    #sends SQL query to the database
    if connection is None:
        raise Exception("Database connection not initialized. Call init() first.")
    with connection.cursor() as cursor:
        cursor.execute(query)
        if query.strip().lower().startswith("select"):
            return cursor.fetchall()
        return cursor.rowcount

def generate_query(voltage, koh_concentration, spectrum):
    # Generates a raw SQL INSERT query string for the measurements table.
    # WARNING: This method has SQL injection risk
    query = (
        f"INSERT INTO measurements (Voltage, KOH_concentration, Spectrum) "
        f"VALUES ({repr(voltage)}, {repr(koh_concentration)}, {repr(spectrum)})"
    )
    return query