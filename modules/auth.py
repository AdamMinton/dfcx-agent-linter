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
    # Check if we are already authenticated in the session
    if "credentials" in st.session_state:
        creds = st.session_state["credentials"]
        project_id = st.session_state.get("project_id", os.environ.get("GCP_PROJECT_ID", ""))
        return creds, project_id

    # Check for OAuth Code in Query Params
    if "code" in st.query_params:
        try:
            code = st.query_params["code"]
            flow = Flow.from_client_secrets_file(
                CLIENT_SECRETS_FILE,
                scopes=SCOPES,
                redirect_uri=get_redirect_uri()
            )
            flow.fetch_token(code=code)
            creds = flow.credentials
            st.session_state["credentials"] = creds
            
            # Clear the code from the URL
            st.query_params.clear()
            st.rerun()
        except Exception as e:
            st.error(f"Authentication failed during token exchange: {e}")
            return None, None

    # If no credentials, show login button
    if os.path.exists(CLIENT_SECRETS_FILE):
        try:
            flow = Flow.from_client_secrets_file(
                CLIENT_SECRETS_FILE,
                scopes=SCOPES,
                redirect_uri=get_redirect_uri()
            )
            auth_url, _ = flow.authorization_url(prompt="consent")
            
            st.sidebar.markdown(f"[Login with Google]({auth_url})")
            st.warning("Please log in using the sidebar link to proceed.")
            return None, None
        except Exception as e:
            st.error(f"Error loading client secrets: {e}")
            # Fallback to default credentials if client secret fails (e.g. in non-interactive env without secrets)
            pass

    # Fallback to Google Default Credentials (useful for local dev without OAuth setup or Service Account)
    try:
        credentials, project_id = google.auth.default()
        
        # Allow overriding project_id from sidebar if needed
        if not project_id:
            # Try to get from env var first
            project_id = os.environ.get("GCP_PROJECT_ID")
            
        if not project_id:
            project_id = st.sidebar.text_input("Enter GCP Project ID", value="")
        
        return credentials, project_id
    except Exception as e:
        st.error(f"Authentication failed: {e}")
        return None, None
