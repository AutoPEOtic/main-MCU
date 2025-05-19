import pymysql

# Global variable to hold the database connection
connection = None

def init(host, user, password, database, port=3306):
    """
    Initializes the connection to the MySQL database.
    Call this function before using send() or other database operations.
    """
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
    """
    Executes a raw SQL query on the connected database.
    For SELECT queries, returns fetched results.
    For other queries, returns the number of affected rows.
    """
    if connection is None:
        raise Exception("Database connection not initialized. Call init() first.")
    with connection.cursor() as cursor:
        cursor.execute(query)
        if query.strip().lower().startswith("select"):
            return cursor.fetchall()
        return cursor.rowcount

def generate_query(voltage, koh_concentration, spectrum):
    """
    Generates a raw SQL INSERT query string for the measurements table.
    WARNING: This method is not safe for untrusted input (SQL injection risk).
    """
    query = (
        f"INSERT INTO measurements (Voltage, KOH_concentration, Spectrum) "
        f"VALUES ({repr(voltage)}, {repr(koh_concentration)}, {repr(spectrum)})"
    )
    return query