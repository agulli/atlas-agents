import sqlite3

def secure_db_query(sql_query: str):
    """
    A protected database querying tool. 
    Rejects common mutations at the Python level before the DB connects.
    NOTE: This is a teaching example, NOT production security. This check
    can be bypassed (e.g. TRUNCATE, embedded comments). In production, use
    a read-only database user or a proper SQL parser.
    """
    banned_ops = ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "GRANT", "TRUNCATE", "REPLACE"]
    if any(op in sql_query.upper() for op in banned_ops):
        return "Error: Read-only access permitted."
        
    try:
        with sqlite3.connect("readonly_replica.db") as conn:
            cursor = conn.cursor()
            cursor.execute(sql_query)
            # Limit returned rows mathematically
            return cursor.fetchmany(50) 
    except Exception as e:
        return f"Query structure invalid: {e}"\n