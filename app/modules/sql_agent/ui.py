import sys
import os

# --- PATH FIX: Add project root to sys.path ---
# This ensures Python can find the 'app' module no matter where you run the command from.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))
# -----------------------------------------------

import streamlit as st
from app.modules.sql_agent.graph import app
from app.modules.sql_agent.tools import list_tables

st.set_page_config(page_title="SQL Sentinel", page_icon="🛡️", layout="wide")

st.title("🛡️ SQL Sentinel: The Self-Healing Agent")
st.markdown("Ask questions about the `Chinook` music database. I will write safe SQL, execute it, and fix my own errors.")

# --- Sidebar: System Monitor ---
with st.sidebar:
    st.header("🔧 System Monitor")
    
    # 1. Show available tables (RAG context)
    st.subheader("Database Schema")
    tables = list_tables()
    st.code("\n".join(tables), language="text")
    
    # 2. Debug Information
    st.subheader("Live Agent State")
    debug_container = st.empty()
    debug_container.info("Waiting for input...")

# --- Chat Interface ---
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Handle Input
if prompt := st.chat_input("Ex: Show me the top 5 selling artists"):
    # 1. User Message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 2. Agent Execution
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        message_placeholder.markdown("Thinking... 🧠")
        
        try:
            # Run the LangGraph
            initial_state = {"question": prompt, "iterations": 0}
            result = app.invoke(initial_state)
            
            # --- Extract Final Answer ---
            final_answer = result.get("query_result", "No answer generated.")
            
            # Update Chat UI
            message_placeholder.markdown(final_answer)
            st.session_state.messages.append({"role": "assistant", "content": final_answer})
            
            # --- Update Sidebar (The "Senior" Demo Feature) ---
            with debug_container.container():
                st.write("**Iterations:**", result["iterations"])
                
                st.write("**Final SQL Generated:**")
                st.code(result.get("sql_query", "None"), language="sql")
                
                if result.get("error"):
                    st.error(f"Last Error Encountered: {result['error']}")
                else:
                    st.success("Execution: Success")
                    
        except Exception as e:
            message_placeholder.error(f"System Crash: {str(e)}")