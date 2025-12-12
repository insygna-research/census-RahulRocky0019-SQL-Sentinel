from typing import List, Any
from sqlalchemy import create_engine, inspect, text
from app.core.config import Config

# Initialize the engine globally using the Config path
engine = create_engine(Config.DB_URI)

def list_tables() -> List[str]:
    """
    Returns a list of all table names in the database.
    Used by the Agent to understand the Schema.
    """
    inspector = inspect(engine)
    return inspector.get_table_names()

def get_schema(table_names: List[str]) -> str:
    """
    Returns the DDL (CREATE TABLE statements) for the specified tables.
    Crucial for the LLM to understand column names and types.
    """
    inspector = inspect(engine)
    schema_text = ""
    
    for table in table_names:
        # Get columns
        columns = inspector.get_columns(table)
        schema_text += f"Table: {table}\n"
        for col in columns:
            schema_text += f" - {col['name']} ({col['type']})\n"
        schema_text += "\n"
        
    return schema_text
    
def run_query(query: str) -> str:
    """
    Executes a SQL query and returns the results as a string.
    
    SAFETY PROTOCOLS:
    1. Catches errors and returns the error message instead of crashing.
    2. Enforces a hard context safety limit to prevent Token Overflow.
    """
    try:
        with engine.connect() as connection:
            result = connection.execute(text(query))
            keys = result.keys()
            all_rows = [dict(zip(keys, row)) for row in result.fetchall()]
            
            # Global Hard Cap (Safety Valve)
            GLOBAL_CAP = 50 
            if len(all_rows) > GLOBAL_CAP:
                preview = all_rows[:GLOBAL_CAP]
                return (
                    f"SYSTEM NOTE: Result truncated. Found {len(all_rows)} rows. "
                    f"Showing first {GLOBAL_CAP}.\nData: {str(preview)}"
                )
            
            if not all_rows:
                return "Result: Empty."
                
            return str(all_rows)
            
    except Exception as e:
        return f"Error: {str(e)}"
