import google.auth
import streamlit as st

def authenticate():
    """
    Authenticates the user using Google Default Credentials.
    Returns:
        credentials (google.auth.credentials.Credentials): The credentials object.
        project_id (str): The project ID.
    """
    try:
        credentials, project_id = google.auth.default()
        
        # Allow overriding project_id from sidebar if needed, but default to auth'd one
        # or the one provided by user if auth default is missing project_id
        if not project_id:
            project_id = st.sidebar.text_input("Enter GCP Project ID", value="att-aam-external")
        
        return credentials, project_id
    except Exception as e:
        st.error(f"Authentication failed: {e}")
        return None, None
