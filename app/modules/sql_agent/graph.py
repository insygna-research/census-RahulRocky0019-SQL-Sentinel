from typing import Literal
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, START, END

from app.core.config import Config
from app.modules.sql_agent.state import AgentState
from app.modules.sql_agent.tools import list_tables, get_schema, run_query
from app.modules.sql_agent.sentinel import is_safe_sql

# --- 1. Setup LLM & Structured Output ---
llm = ChatGroq(
    api_key=Config.GROQ_API_KEY, 
    model=Config.MODEL_1, 
    temperature=0
)

class SQLOutput(BaseModel):
    """Force the LLM to explain its reasoning before writing code."""
    explanation: str = Field(description="Brief explanation of the logic.")
    query: str = Field(description="The valid SQLite query.")

# --- 2. Nodes ---

def parse_question(state: AgentState):
    """
    Step 1: Understand the context. 
    For MVP, we just load the full schema (Chinook is small).
    """
    return {"iterations": 0, "error": None}

def generate_sql(state: AgentState):
    """
    Step 2: Generate SQL based on the question and schema.
    If there is an error from a previous run, it sees it in 'state'.
    """
    tables = list_tables()
    schema_text = get_schema(tables)
    
    system_msg = """You are an expert SQL Data Analyst. 
    Given the schema below, write a SQLite query to answer the user's question.
    
    Schema:
    {schema}
    
    Rules:
    1. STRICTLY use the provided column names.
    2. Do not use Markdown formatting (```sql). Just the raw query in the JSON.
    """
    
    # Dynamic prompt that changes if an error exists (Self-Correction)
    user_msg = f"Question: {state['question']}"
    if state.get("error"):
        user_msg += f"\n\nPREVIOUS ERROR: {state['error']}\nFix the query based on this error."

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_msg),
        ("user", user_msg)
    ])
    
    # We use 'with_structured_output' to enforce strict JSON
    structured_llm = llm.with_structured_output(SQLOutput)
    chain = prompt | structured_llm
    
    try:
        response = chain.invoke({"schema": schema_text})
        return {"sql_query": response.query, "iterations": state["iterations"] + 1}
    except Exception as e:
        # If the LLM output breaks structure (rare), fallback
        return {"error": f"LLM Generation Error: {str(e)}"}

def execute_sql(state: AgentState):
    """
    Step 3: The Sentinel Check + Execution.
    """
    query = state["sql_query"]
    
    # Security Check
    if not is_safe_sql(query):
        return {"error": "Security Alert: Dangerous SQL detected (DROP/DELETE/etc)."}
    
    # Execution
    result = run_query(query)
    
    # Check if result looks like a DB error (run_query returns "Error: ..." string on fail)
    if result.startswith("Error:"):
        return {"error": result}
    
    return {"query_result": result, "error": None}

def synthesize_answer(state: AgentState):
    """
    Step 4: Turn the raw list of dicts into a human answer.
    """
    prompt = ChatPromptTemplate.from_template(
        """User Question: {question}
        SQL Query Used: {query}
        SQL Result: {result}
        
        Write a concise, professional answer based strictly on the result."""
    )
    chain = prompt | llm
    response = chain.invoke({
        "question": state["question"],
        "query": state["sql_query"],
        "result": state["query_result"]
    })
    return {"query_result": response.content}

# --- 3. Edge Logic (The Router) ---

def should_continue(state: AgentState) -> Literal["generate_sql", "synthesize_answer", END]:
    """
    Decides if we loop back or finish.
    """
    # Safety Valve: Don't loop forever
    if state["iterations"] > 3:
        return END
        
    if state.get("error"):
        return "generate_sql"  # Loop back to fix the error
    
    return "synthesize_answer" # Success

# --- 4. Build Graph ---

workflow = StateGraph(AgentState)

# Add Nodes
workflow.add_node("parse_question", parse_question)
workflow.add_node("generate_sql", generate_sql)
workflow.add_node("execute_sql", execute_sql)
workflow.add_node("synthesize_answer", synthesize_answer)

# Add Edges
workflow.add_edge(START, "parse_question")
workflow.add_edge("parse_question", "generate_sql")
workflow.add_edge("generate_sql", "execute_sql")

# Conditional Edge (The Loop)
workflow.add_conditional_edges(
    "execute_sql",
    should_continue,
    {
        "generate_sql": "generate_sql",
        "synthesize_answer": "synthesize_answer",
        END: END
    }
)

workflow.add_edge("synthesize_answer", END)

# Compile
app = workflow.compile()