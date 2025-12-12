from typing import Literal
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
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

class RouteDecision(BaseModel):
    intent: Literal["general", "sql"] = Field(
        description="Select 'sql' if the user asks about data/database. Select 'general' if it is a greeting or small talk."
    )

# --- 2. Nodes ---

def parse_question(state: AgentState):
    """
    Step 1 (The Router): Classify the user's intent.
    Does NOT write SQL. Just decides WHERE to go next.
    """
    system_msg = """You are an Intent Classifier. 
    Analyze the user's input and decide:
    1. 'sql': If the user is asking for data, lists, counts, or information that lives in a database.
    2. 'general': If the user is just saying hello, thank you, or asking general questions (e.g. "How are you?").
    """
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_msg),
        ("user", "{question}")
    ])
    
    classifier = llm.with_structured_output(RouteDecision)
    chain = prompt | classifier
    
    decision = chain.invoke({"question": state["question"]})
    
    return {"intent": decision.intent, "iterations": 0, "error": None}


def general_chat(state: AgentState):
    """
    New Node: Handles non-SQL conversation.
    """
    history_msgs = state["chat_history"][-10:]  # Last 10 messages
    msg = state["question"]

    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a helpful Data Assistant named 'SQL Sentinel'. You help users query their SQLite databases. Be concise, professional, and friendly. If the user asks a question about data, politely suggest they ask 'Show me...' or 'List...' so you can query the database."),
        MessagesPlaceholder(variable_name="history"), # <--- Auto-expands the list of messages
        ("user", "{question}")
    ])

    chain = prompt | llm
    response = chain.invoke({
        "history": history_msgs,
        "question": msg
    })
    
    return {"query_result": response.content}


def generate_sql(state: AgentState):
    """
    Step 2: Generate SQL based on the question and schema.
    If there is an error from a previous run, it sees it in 'state'.
    """
    tables = list_tables()
    schema_text = get_schema(tables)
    history_text = "\n".join([f"{msg.type.upper()}: {msg.content}" for msg in state["chat_history"][-10:]]) # Keep last 10 turns

    # --- ARCHITECT-LEVEL PROMPT (DATABASE AGNOSTIC) ---
    system_msg = """You are a Principal SQL Architect. Your goal is to answer user questions by writing efficient, error-free SQLite queries for ANY provided schema.

    ### DATABASE SCHEMA
    {schema}

    ### CRITICAL RULES
    1. **Schema Reliance**: 
       - Strictly use ONLY the tables and columns listed in the schema above. 
       - Do not assume column names (e.g., don't use 'user_id' unless you see it in the schema).
       - Infer relationships based on Foreign Keys or matching ID columns (e.g., 'ArtistId' in 'Albums' links to 'Artists').

    2. **The "Total Count" Protocol (MANDATORY)**:
       - When the user asks for a LIST of records (e.g., "Show tracks"), you MUST limit rows for safety BUT you must also calculate the total count.
       - **Technique**: Use `COUNT(*) OVER() AS _Total_Rows` in your SELECT statement.
       - **Example**: 
         `SELECT Name, AlbumId, COUNT(*) OVER() AS _Total_Rows FROM Tracks LIMIT 20`
       - This allows the user to see "Page 1 of X" without fetching all X rows.

    3. **Aggregations**: 
       - If the user asks for a simple count (e.g. "How many tracks?"), just use `SELECT COUNT(*)`. Do not add the window function.
    
    4. **String Matching (SQLite Specific)**: 
       - SQLite is case-sensitive. When searching for text, assume the user might use wrong casing.
       - Use `UPPER(Column) = 'VALUE'` or `Column LIKE '%Value%'` for robustness.
    
    5. **No DML Operations**: 
       - You are **READ-ONLY**. 
       - If the user asks for a DML operation (INSERT, UPDATE, DELETE, DROP, ALTER), you **MUST NOT** generate a SELECT query to "be helpful".
       - Instead, you **MUST** output exactly this query: `SELECT 'DML_ERROR' AS Error_Message`
       - This triggers a special security handler in the system.

    ### FAILURE RECOVERY
    If a previous query failed, analyze the error provided below.
    """
    
    user_msg = f"""
    ### CHAT HISTORY
    {history_text}
    
    ### CURRENT QUESTION
    {state['question']}
    """

    if state.get("error"):
        user_msg += f"\n\nPREVIOUS ERROR: {state['error']}\nFix the query based on this error."

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_msg),
        ("user", user_msg)
    ])
    
    structured_llm = llm.with_structured_output(SQLOutput)
    chain = prompt | structured_llm
    
    try:
        response = chain.invoke({"schema": schema_text})
        return {
            "sql_query": response.query,
            "explanation": response.explanation,
            "iterations": state["iterations"] + 1
        }
    except Exception as e:
        # If the LLM output breaks structure (rare), fallback
        return {"error": f"LLM Generation Error: {str(e)}"}


def execute_sql(state: AgentState):
    """
    Step 3: The Sentinel Check + Execution.
    """
    query = state["sql_query"]

    # Check for our "Trap Door" Query
    if "DML_ERROR" in query:
        return {"error": "Security Alert: You do not have permission to modify the database (INSERT/UPDATE/DELETE/DROP)."}

    # Backup in case the LLM ignores the prompt
    if not is_safe_sql(query):
        return {"error": "Security Alert: Dangerous SQL detected (DROP/DELETE/etc).."}
       
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
        """You are a Data Reporter. Your job is to present the SQL results to the user clearly.

        User Question: {question}
        SQL Query: {query}
        Raw Data: {result}
        
        ### RESPONSE RULES:
        1. **If the Raw Data is an Error**: Explain what went wrong in plain English.
        
        2. **If the Raw Data is a List**:
           - check for the key `_Total_Rows` inside the data.
           - **Headline**: State "Found [X] records" (using _Total_Rows if present, otherwise count the rows).
           - **Table**: Output the data as a Markdown Table.
           - **Cleanup**: Do NOT include `_Total_Rows` as a column in the table.
        
        3. **If the Raw Data is a Single Number**:
           - Answer directly (e.g., "The total sales were $500.").
        """
    )
    chain = prompt | llm
    response = chain.invoke({
        "question": state["question"],
        "query": state["sql_query"],
        "result": state["query_result"]
    })
    return {"query_result": response.content}

# --- 3. Edge Logic (The Router) ---

def route_decision(state: AgentState) -> Literal["general_chat", "generate_sql"]:
    """
    Decides where to go after 'parse_question'.
    """
    if state["intent"] == "general":
        return "general_chat"
    return "generate_sql"


def should_continue(state: AgentState) -> Literal["generate_sql", "synthesize_answer", "END"]:
    """
    Decides if we loop back or finish.
    """
    # Safety Valve: Don't loop forever
    if state["iterations"] > 3:
        return "END"
        
    if state.get("error"):
        return "generate_sql"  # Loop back to fix the error
    
    return "synthesize_answer" # Success

# --- 4. Build Graph ---

workflow = StateGraph(AgentState)

workflow.add_node("parse_question", parse_question)
workflow.add_node("general_chat", general_chat)
workflow.add_node("generate_sql", generate_sql)
workflow.add_node("execute_sql", execute_sql)
workflow.add_node("synthesize_answer", synthesize_answer)

workflow.add_edge(START, "parse_question")

workflow.add_conditional_edges(
    "parse_question",
    route_decision,
    {
        "general_chat": "general_chat",
        "generate_sql": "generate_sql"
    }
)

workflow.add_edge("generate_sql", "execute_sql")

workflow.add_conditional_edges(
    "execute_sql",
    should_continue,
    {
        "generate_sql": "generate_sql",
        "synthesize_answer": "synthesize_answer",
        "END": END
    }
)

workflow.add_edge("general_chat", END)
workflow.add_edge("synthesize_answer", END)

# Compile
app = workflow.compile()
