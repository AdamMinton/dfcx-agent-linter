# Deployment Instructions

## Prerequisites

1.  **GCP Project**: Ensure you have a GCP project (e.g., `my-gcp-project`).
    *   (Optional) Set `GCP_PROJECT_ID` environment variable locally or in Cloud Run to pre-fill the project ID.
2.  **OAuth Client ID**:
    *   Go to **APIs & Services > Credentials**.
    *   Create an **OAuth 2.0 Client ID** (Web application).
    *   **Authorized Redirect URIs**:
        *   Local: `http://localhost:8501`
        *   Cloud Run: `https://<YOUR-SERVICE-NAME>-<HASH>.a.run.app` (Update this after first deploy).
    *   Download the JSON file and save it as `client_secret.json` in the root of this repository.

## Local Development

1.  **Install Dependencies**:
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    ```

2.  **Run Locally**:
    ```bash
    streamlit run app.py
    ```

## Cloud Run Deployment

### Option 1: Using Cloud Build (Recommended)

This method builds the container and deploys it to Cloud Run.

1.  **Submit Build**:
    ```bash
    gcloud builds submit --config cloudbuild.yaml .
    ```

2.  **Post-Deployment Configuration**:
    *   Get the Service URL from the output (e.g., `https://dfcx-linter-app-244644527824.us-central1.run.app`).
    *   Go back to **APIs & Services > Credentials** in GCP Console.
    *   Add the Service URL to the **Authorized Redirect URIs** of your OAuth Client.
    *   (Optional) Update the `REDIRECT_URI` environment variable in Cloud Run if it differs from the default logic (though the code currently defaults to localhost or tries to infer, setting it explicitly is safer).
        ```bash
        gcloud run services update dfcx-linter-app \
          --update-env-vars REDIRECT_URI=<YOUR_SERVICE_URL> \
          --region us-central1
        ```

### Option 2: Manual Gcloud Deploy

```bash
gcloud run deploy dfcx-linter-app \
  --source . \
  --project <YOUR_PROJECT_ID> \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars REDIRECT_URI=https://dfcx-linter-app-244644527824.us-central1.run.app
```

*Note: We use `--allow-unauthenticated` because the application handles authentication internally via OAuth.*
