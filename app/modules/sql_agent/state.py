from typing import TypedDict, Annotated, Optional, Any, List
from langchain_core.messages import BaseMessage
from operator import add

class AgentState(TypedDict):
    """
    State specific to the SQL Agent workflow.
    """
    question: str
    intent: str
    chat_history: List[BaseMessage]
    sql_query: Optional[str]
    explanation: Optional[str]
    query_result: Optional[str]
    error: Optional[str]
    iterations: int