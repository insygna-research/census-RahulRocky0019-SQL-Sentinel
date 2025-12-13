from typing import Literal, TypedDict
from langgraph.graph import StateGraph, START, END

# --- 1. Define Dummy State ---
class AgentState(TypedDict):
    question: str
    intent: str
    sql_query: str
    error: str
    iterations: int

# --- 2. Define Dummy Nodes (No Logic, just for visualization) ---
def parse_question(state): return {}
def general_chat(state): return {}
def generate_sql(state): return {}
def execute_sql(state): return {}
def synthesize_answer(state): return {}

# --- 3. Define Dummy Logic for Conditionals ---
def route_decision(state) -> Literal["general_chat", "generate_sql"]:
    return "generate_sql"

def should_continue(state) -> Literal["generate_sql", "synthesize_answer", "END"]:
    return "synthesize_answer"

# --- 4. Build the Graph Structure ---
workflow = StateGraph(AgentState)

# Add Nodes
workflow.add_node("parse_question", parse_question)
workflow.add_node("general_chat", general_chat)
workflow.add_node("generate_sql", generate_sql)
workflow.add_node("execute_sql", execute_sql)
workflow.add_node("synthesize_answer", synthesize_answer)

# Add Edges
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
        "generate_sql": "generate_sql",      # The Self-Healing Loop
        "synthesize_answer": "synthesize_answer",
        "END": END
    }
)

workflow.add_edge("general_chat", END)
workflow.add_edge("synthesize_answer", END)

# --- 5. Generate and Save Image ---
app = workflow.compile()

try:
    # This generates the PNG data
    png_data = app.get_graph().draw_mermaid_png()
    
    # Save to file
    with open("architecture_diagram.png", "wb") as f:
        f.write(png_data)
    
    print("✅ Success! Graph saved as 'architecture_diagram.png'")
    print("You can now copy-paste this image into Slide 6.")
    
except Exception as e:
    print("❌ Error generating image. Do you have the dependencies installed?")
    print("Try running: pip install langgraph parsing")
    print(f"Details: {e}")