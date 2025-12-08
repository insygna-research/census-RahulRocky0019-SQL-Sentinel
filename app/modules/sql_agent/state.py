from typing import TypedDict, Optional, Any, List

class AgentState(TypedDict):
    """
    State specific to the SQL Agent workflow.
    """
    question: str
    intent: str
    sql_query: Optional[str]
    query_result: Optional[str]
    error: Optional[str]
    iterations: int