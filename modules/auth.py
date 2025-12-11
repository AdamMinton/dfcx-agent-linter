import os
import google.auth
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
import streamlit as st

# Constants
CLIENT_SECRETS_FILE = "client_secret.json"
SCOPES = [
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/dialogflow"
]

def get_redirect_uri():
    """Determines the redirect URI based on the environment."""
    # In Cloud Run, we might need to set this env var or infer it.
    # For now, we'll default to localhost for local dev, and expect an env var for prod
    # or we can try to infer from st.context if available (experimental)
    # But simplest is to let the user configure it or default to localhost.
    
    # If running in Cloud Run, the service URL should be used.
    # We can use a helper to detect if we are local or not, but for the initial auth flow,
    # we need to match what's in the Console.
    
    # We will try to grab it from an environment variable 'REDIRECT_URI'
    # If not set, default to localhost.
    return os.environ.get("REDIRECT_URI", "http://localhost:8501")

def authenticate():
    """
    Authenticates the user using OAuth 2.0 or Google Default Credentials.
    Returns:
        credentials (google.auth.credentials.Credentials): The credentials object.
        project_id (str): The project ID.
    """
    creds = None
    
    # Check if we are already authenticated in the session
    if "credentials" in st.session_state:
        creds = st.session_state["credentials"]

    # Check for OAuth Code in Query Params
    if not creds and "code" in st.query_params:
        try:
            code = st.query_params["code"]
            
            # Retrieve state to restore params
            state = st.query_params.get("state")
            
            flow = Flow.from_client_secrets_file(
                CLIENT_SECRETS_FILE,
                scopes=SCOPES,
                redirect_uri=get_redirect_uri()
            )
            flow.fetch_token(code=code)
            creds = flow.credentials
            st.session_state["credentials"] = creds
            
            # Clear the code/state from the URL
            st.query_params.clear()
            
            # Restore params from state if valid
            if state:
                import json
                try:
                    restored_params = json.loads(state)
                    # Convert list values to single values if needed, dependent on Streamlit version
                    # st.query_params updates accept dict.
                    st.query_params.update(restored_params)
                except Exception as e:
                    print(f"Failed to restore state parameters: {e}")

            st.rerun()
        except Exception as e:
            st.error(f"Authentication failed during token exchange: {e}")
            return None, None

    # If no credentials, show login button
    if not creds and os.path.exists(CLIENT_SECRETS_FILE):
        try:
            flow = Flow.from_client_secrets_file(
                CLIENT_SECRETS_FILE,
                scopes=SCOPES,
                redirect_uri=get_redirect_uri()
            )
            
            # Capture current params as state
            import json
            current_params = dict(st.query_params)
            state = json.dumps(current_params)
            
            auth_url, _ = flow.authorization_url(prompt="consent", state=state)
            
            st.sidebar.markdown(f'<a href="{auth_url}" target="_self">Login with Google</a>', unsafe_allow_html=True)
            st.warning("Please log in using the sidebar link to proceed.")
            return None, None
        except Exception as e:
            st.error(f"Error loading client secrets: {e}")
            # Fallback to default credentials if client secret fails
            pass

    # Fallback to Google Default Credentials
    if not creds:
        try:
            creds, _ = google.auth.default()
        except Exception as e:
            st.error(f"Authentication failed: {e}")
            return None, None

    # If we have credentials, show the Project ID input
    if creds:
        # Initialize project_id in session state if not present
        if "project_id" not in st.session_state:
            # Check URL param first, then env var, then empty
            url_project = st.query_params.get("project_id", "")
            st.session_state["project_id"] = url_project if url_project else os.environ.get("GCP_PROJECT_ID", "")
            
        # Always show the input field
        project_id = st.sidebar.text_input("Enter GCP Project ID", key="project_id")
        
        return creds, project_id
        
    return None, None
