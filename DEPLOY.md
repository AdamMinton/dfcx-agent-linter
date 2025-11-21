# Deployment Instructions

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

1.  **Build and Deploy**:
    Run the following command to deploy to Cloud Run. Replace `REGION` with your preferred region (e.g., `us-central1`).

    ```bash
    gcloud run deploy dfcx-linter-app \
      --source . \
      --project att-aam-external \
      --region us-central1 \
      --allow-unauthenticated
    ```

    *Note: Remove `--allow-unauthenticated` if you want to restrict access.*
