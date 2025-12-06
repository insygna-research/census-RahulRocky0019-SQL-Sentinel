import re

def is_safe_sql(query: str) -> bool:
    """
    Static analysis to reject dangerous SQL commands.
    Returns True if safe, False if dangerous.
    """
    if not query:
        return False

    q = query.strip().upper()
    
    # Strict Blocklist
    forbidden_keywords = [
        "DROP", "DELETE", "TRUNCATE", "ALTER", "GRANT", "REVOKE", 
        "INSERT", "UPDATE", "REPLACE"
    ]
    
    for keyword in forbidden_keywords:
        pattern = r'\b' + keyword + r'\b'   # Regex \b ensures we match 'DROP' but not 'DROPBOX'
        if re.search(pattern, q):
            return False
            
    return True