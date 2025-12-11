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
    
    # Locations
    locations = ["global", "us-central1", "us-east1", "us-west1", "australia-southeast1", "europe-west1", "europe-west2", "asia-northeast1"]
    
    # 1. Handle Location Selection
    # Initialize from URL if not in session state, or if URL changed?
    # Actually, we want the widget to drive the URL, and URL to drive defaults.
    # Streamlit widgets persist state.
    
    # Check URL for location default
    url_location = st.query_params.get("location", "global")
    if url_location not in locations:
        url_location = "global"
        
    # We can't easily set the 'value' of a selectbox if it's already in session state with a different value
    # But we can default it if it's NOT in session state.
    # OR we can force it if we want URL to be truth.
    # Let's trust session_state if it exists? No, if user pastes a URL, they expect THAT location.
    # But if they change the dropdown, session_state updates.
    # We should sync: URL -> Default for Widget. Widget Change -> Update URL.
    
    # To make URL the source of truth on first load, we can check if we've "processed" the URL yet?
    # Or just rely on standard Streamlit flow:
    # If key is in session_state, it uses that.
    # We can set the key in session_state before rendering the widget if we want to force it.
    
    # Let's try to set default_index based on URL if widget key not in session state?
    # Actually simpler: just update query params when value changes.
    # But for "landing" on a URL, we need to read it.
    
    try:
        loc_index = locations.index(url_location)
    except ValueError:
        loc_index = 0

    location = st.sidebar.selectbox(
        "Select Location",
        locations,
        index=loc_index,
        key="selected_location"
    )
    
    # Sync Location to URL
    if location != st.query_params.get("location"):
        st.query_params["location"] = location

    # Sync Project ID to URL (auth might have done it, but let's be safe)
    if project_id and project_id != st.query_params.get("project_id"):
        st.query_params["project_id"] = project_id
    
    if project_id and location:
        with st.spinner(f"Fetching agents from {project_id}/{location}..."):
            agents = list_agents(credentials, project_id, location)
            
        if agents:
            agent_names = [a["display_name"] for a in agents]
            
            # Check URL for agent (expecting Agent ID now)
            url_agent_id = st.query_params.get("agent", "")
            
            # Find index if possible
            agent_index = 0
            if url_agent_id:
                # Try to match by Agent ID (resource name)
                matching_agent = next((a for a in agents if a["name"] == url_agent_id), None)
                if matching_agent:
                    # If found, find the index of its display name
                    try:
                        agent_index = agent_names.index(matching_agent["display_name"])
                    except ValueError:
                        agent_index = 0
            
            selected_agent_name = st.sidebar.selectbox(
                "Select Agent", 
                agent_names, 
                index=agent_index,
                key="selected_agent"
            )
            
            # Find the full agent object
            selected_agent = next((a for a in agents if a["display_name"] == selected_agent_name), None)
            
            # Sync Agent ID to URL
            if selected_agent:
                if selected_agent["name"] != st.query_params.get("agent"):
                    st.query_params["agent"] = selected_agent["name"]

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
