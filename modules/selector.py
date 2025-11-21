import streamlit as st
from google.cloud import dialogflowcx_v3
from google.oauth2 import service_account

def list_agents(credentials, project_id, location="global"):
    """Lists DFCX agents in a given project and location."""
    try:
        client_options = None
        if location != "global":
            api_endpoint = f"{location}-dialogflow.googleapis.com:443"
            client_options = {"api_endpoint": api_endpoint}

        client = dialogflowcx_v3.AgentsClient(credentials=credentials, client_options=client_options)
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
    """Renders the agent selection widgets."""
    
    col1, col2 = st.columns(2)
    
    with col1:
        location = st.selectbox(
            "Select Location",
            ["global", "us-central1", "us-east1", "us-west1", "australia-southeast1", "europe-west1", "europe-west2", "asia-northeast1"],
            index=0
        )
    
    if project_id and location:
        with st.spinner(f"Fetching agents from {project_id}/{location}..."):
            agents = list_agents(credentials, project_id, location)
            
        if agents:
            agent_names = [a["display_name"] for a in agents]
            selected_agent_name = st.selectbox("Select Agent", agent_names)
            
            # Find the full agent object
            selected_agent = next((a for a in agents if a["display_name"] == selected_agent_name), None)
            return selected_agent
        else:
            st.warning("No agents found in this location.")
            return None
    return None
