import streamlit as st
from modules import auth, selector, linter, ssml_linter, graph_linter, search_linter, test_runner

st.set_page_config(page_title="DFCX Agent Linter", layout="wide")

def main():
    st.title("DFCX Agent Linter & Tester")
    
    # Sidebar for Authentication and Configuration
    st.sidebar.header("Configuration")
    
    # Authentication
    creds, project_id = auth.authenticate()
    
    if not creds:
        st.warning("Please authenticate to proceed.")
        return

    st.sidebar.success(f"Authenticated as: {project_id}")
    
    # Agent Selection
    st.header("1. Select Agent")
    agent_details = selector.render_selector(creds, project_id)
    
    if agent_details:
        st.success(f"Selected Agent: {agent_details['display_name']}")
        
        # Modules Area
        st.header("2. Run Modules")
        
        tab1, tab2, tab3, tab4, tab5 = st.tabs(["CXLint", "SSML Checker", "Graph Linter", "Search", "Test Runner"])
        
        with tab1:
            linter.render_linter(creds, agent_details)
            
        with tab2:
            ssml_linter.render_ssml_linter(creds, agent_details)

        with tab3:
            graph_linter.render_graph_linter(creds, agent_details)

        with tab4:
            search_linter.render_search_linter(creds, agent_details)

        with tab5:
            test_runner.render_test_runner(creds, agent_details)

if __name__ == "__main__":
    main()
