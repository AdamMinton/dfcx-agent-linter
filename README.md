# DFCX Agent Linter Web App

A composable web application built with Streamlit to run automated tests and linting on Dialogflow CX (DFCX) agents. The current version integrates `cxlint` to provide comprehensive quality checks for your agents.

## Features

- **Authentication**: Securely authenticate with Google Cloud using local credentials or Cloud Run service identity.
- **Agent Selection**: Browse and select DFCX agents across different GCP projects and locations.
- **Automated Linting**: Run `cxlint` on selected agents to identify issues such as:
    - Unreachable pages
    - Missing training phrases
    - Naming convention violations
    - Invalid intents in test cases
- **Rich Reporting**: View detailed linting reports directly within the web interface.

## Project Structure

```
.
├── app.py                 # Main Streamlit application entry point
├── modules/               # Application modules
│   ├── auth.py            # Google Cloud authentication logic
│   ├── selector.py        # DFCX agent selection widgets
│   └── linter.py          # cxlint runner and monkeypatches
├── requirements.txt       # Python dependencies
├── Dockerfile             # Container configuration for Cloud Run
├── DEPLOY.md              # Detailed deployment instructions
└── README.md              # This file
```

## Local Development

### Prerequisites

- Python 3.9+
- Google Cloud SDK (`gcloud`) installed and authenticated
- A Google Cloud Project with Dialogflow API enabled

### Setup

1.  **Clone the repository:**
    ```bash
    git clone <repository-url>
    cd dfcx-agent-linter
    ```

2.  **Create and activate a virtual environment:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Run the application:**
    ```bash
    streamlit run app.py
    ```

5.  **Access the app:**
    Open your browser and navigate to `http://localhost:8501`.

## Deployment to Cloud Run

This application is containerized and ready for deployment on Google Cloud Run.

1.  **Build the container image:**
    ```bash
    gcloud builds submit --tag gcr.io/PROJECT_ID/dfcx-linter
    ```

2.  **Deploy to Cloud Run:**
    ```bash
    gcloud run deploy dfcx-linter \
      --image gcr.io/PROJECT_ID/dfcx-linter \
      --platform managed \
      --region us-central1 \
      --allow-unauthenticated
    ```

For more detailed instructions, refer to [DEPLOY.md](DEPLOY.md).

## Troubleshooting

### Common Issues

-   **MarkupError / UnboundLocalError**: The `cxlint` library has some known issues with rich text formatting and variable initialization. This application includes robust monkeypatches in `modules/linter.py` to handle these edge cases automatically.
-   **Authentication Errors**: Ensure your local environment has Application Default Credentials set up (`gcloud auth application-default login`) or that the Cloud Run service account has the necessary permissions (`roles/dialogflow.client`).

## Contributing

Contributions are welcome! Please submit a Pull Request with your changes.
