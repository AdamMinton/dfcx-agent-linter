import streamlit as st
from google.cloud import dialogflowcx_v3
from google.oauth2 import service_account

@st.cache_data(ttl=600)
def list_agents(_credentials, project_id, location="global"):
    """Lists DFCX agents in a given project and location."""
    try:
        client_options = None
        if location != "global":
            api_endpoint = f"{location}-dialogflow.googleapis.com:443"
            client_options = {"api_endpoint": api_endpoint}

        client = dialogflowcx_v3.AgentsClient(credentials=_credentials, client_options=client_options)
        parent = f"projects/{project_id}/locations/{location}"
        
        request = dialogflowcx_v3.ListAgentsRequest(parent=parent)
        page_result = client.list_agents(request=request)
        
        agents = []
        for agent in page_result:
            agents.append({
                "display_name": agent.display_name,
                "name": agent.name,
                "location": location
            })
        return agents
    except Exception as e:
        st.error(f"Error listing agents in {location}: {e}")
        return []

def render_selector(credentials, project_id):
    """Renders the agent selection widgets in the sidebar."""
    
    st.sidebar.header("Agent Selection")
    
    location = st.sidebar.selectbox(
        "Select Location",
        ["global", "us-central1", "us-east1", "us-west1", "australia-southeast1", "europe-west1", "europe-west2", "asia-northeast1"],
        index=0
    )
    
    if project_id and location:
        with st.spinner(f"Fetching agents from {project_id}/{location}..."):
            agents = list_agents(credentials, project_id, location)
            
        if agents:
            agent_names = [a["display_name"] for a in agents]
            selected_agent_name = st.sidebar.selectbox("Select Agent", agent_names)
            
            # Find the full agent object
            selected_agent = next((a for a in agents if a["display_name"] == selected_agent_name), None)

            # Check if agent has changed
            if "last_selected_agent_name" not in st.session_state:
                st.session_state["last_selected_agent_name"] = None
            
            current_agent_name = selected_agent["name"] if selected_agent else None
            
            if current_agent_name != st.session_state["last_selected_agent_name"]:
                # Clear results from other modules
                keys_to_clear = [
                    "cxlint_results",
                    "cxlint_report_content",
                    "ssml_issues",
                    "graph_issues",
                    "test_runner_result",
                    "test_runner_df",
                    "flows_map",
                    "available_tags"
                ]
                for key in keys_to_clear:
                    if key in st.session_state:
                        del st.session_state[key]
                
                st.session_state["last_selected_agent_name"] = current_agent_name
                # Rerun to reflect cleared state immediately if needed, but usually Streamlit handles this on next interaction.
                # However, since we are inside the render loop, the downstream modules will check session state.
                # If we just cleared it, they will see empty state, which is what we want.

            return selected_agent
        else:
            st.sidebar.warning("No agents found in this location.")
            return None
    return None
