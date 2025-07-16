import pymysql
import settings.config as config

class database():
    def __init__(self):
        self.database = pymysql.connect(host=config.database_host,
                                          user=config.database_user,
                                          password=config.database_password,
                                          database=config.database_name,
                                          port=config.database_port,
                                          cursorclass=pymysql.cursors.DictCursor,
                                          autocommin=True)


    def send(self, query):
        #sends SQL query to the database
        if self.database is None:
            raise Exception("Database connecting not initialized. Call init() first.")
        with self.database.cursor() as cursor:
            cursor.execute(query)
            if query.strip().lower().startswith("select"):
                return cursor.fetchall()
            return cursor.rowcount

    def generate_query(self, spectrum):
        # Generates a raw SQL INSERT query string for the measurements table.
        # WARNING: This method has SQL injection risk
        query = (
            f"INSERT INTO measurements (Voltage, KOH_concentration, Spectrum) "
            f"VALUES ({repr(config.PEO_Upos)}, {repr(config.desired_concentration)}, {repr(spectrum)})"
        )
        return query