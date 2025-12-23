import streamlit as st
from google.cloud import dlp_v2
import json
import pandas as pd

def list_templates(client, project_id, template_type="inspect"):
    """Lists DLP templates."""
    parent = f"projects/{project_id}/locations/global" # Standardize on global for now
    try:
        if template_type == "inspect":
            response = client.list_inspect_templates(request={"parent": parent})
            return {t.name: t.display_name or t.name for t in response}
        elif template_type == "deidentify":
            response = client.list_deidentify_templates(request={"parent": parent})
            return {t.name: t.display_name or t.name for t in response}
    except Exception as e:
        # st.error(f"Error listing {template_type} templates: {e}")
        return {}

def render_dlp_simulator(creds, project_id):
    st.header("DLP Simulator")
    st.markdown("Inspect and de-identify text using Google Cloud DLP.")

    if not project_id:
        st.warning("Please select a GCP Project ID in the sidebar.")
        return

    # Tabs for different functions
    tab1, tab2 = st.tabs(["Simulator", "Configuration"])
    
    # Initialize Client once if possible or on demand
    try:
        dlp_client = dlp_v2.DlpServiceClient(credentials=creds)
    except Exception as e:
        st.error(f"Failed to initialize DLP Client: {e}")
        return

    with tab2:
        st.subheader("DLP Settings")
        
        # Fetch Templates
        with st.spinner("Fetching DLP Templates..."):
            inspect_templates_map = list_templates(dlp_client, project_id, "inspect")
            deid_templates_map = list_templates(dlp_client, project_id, "deidentify")
        
        # Dropdowns
        # Flip map for display: Display Name -> Resource Name
        inspect_options = {"(None) - Use Default": None}
        for name, display in inspect_templates_map.items():
            inspect_options[f"{display} ({name.split('/')[-1]})"] = name
            
        deid_options = {"(None) - Use Default (Masking)": None}
        for name, display in deid_templates_map.items():
            deid_options[f"{display} ({name.split('/')[-1]})"] = name

        selected_inspect_label = st.selectbox("Inspect Template", options=list(inspect_options.keys()))
        inspect_template = inspect_options[selected_inspect_label]

        selected_deid_label = st.selectbox("De-identify Template", options=list(deid_options.keys()))
        deidentify_template = deid_options[selected_deid_label]
        
        st.info("If no Inspect Template is provided, a default configuration detecting EMAIL_ADDRESS, PHONE_NUMBER, CREDIT_CARD_NUMBER, and US_SSN will be used.")

        # Key Exception List
        DEFAULT_EXCEPTIONS = [
            "avaya-session-telephone", "input_from_ivrcs", "head_intent", "ChargeChangeId", 
            "TN", "BillsOnID", "productsOnID", "ProvidedSecondaryTn", "Taskcounter", 
            "ProvidedZipCode", "SMSType", "UserProvidedDataUnknown", "VerintID", 
            "AAMIntentFromGDF", "providedIntent", "previousproductline", "from_taskRouter", 
            "taskList", "ProvidedContactTn", "goal", "ProvidedIDMatchedToBill"
        ]
        
        st.subheader("Key Inspection Settings")
        exception_keys_str = st.text_area(
            "Exception Keys (one per line)", 
            value="\n".join(DEFAULT_EXCEPTIONS),
            height=200,
            help="Keys listed here will be SKIPPED during Key-Level Analysis."
        )
        exception_keys = set(k.strip() for k in exception_keys_str.splitlines() if k.strip())
        
        
        # Max Depth Control
        st.subheader("Simulation Parameters")
        max_depth = st.number_input("Max Nesting Depth (0 = No Limit)", min_value=0, value=0, help="Stop flattening after this depth and treat the remaining subtree as a single string. Useful for simulating 'clumped' payloads.")
        
        # Shared inspect config for both modes
        inspect_config = None
        if not inspect_template:
            info_types = [{"name": "EMAIL_ADDRESS"}, {"name": "PHONE_NUMBER"}, {"name": "CREDIT_CARD_NUMBER"}, {"name": "US_SOCIAL_SECURITY_NUMBER"}]
            inspect_config = {"info_types": info_types, "include_quote": True}
        
        # Shared deid config
        deid_config = None
        if not deidentify_template:
                 deid_config = {
                    "info_type_transformations": {
                        "transformations": [
                            {
                                "primitive_transformation": {
                                    "character_mask_config": {
                                        "masking_character": "*"
                                    }
                                }
                            }
                        ]
                    }
                }

    with tab1:
        # Mode Selection
        mode = st.radio("Analysis Mode", ["JSON Key-Level", "General Text"], horizontal=True)
        
        st.subheader("Input")
        text_input = st.text_area("Enter content to inspect:", height=200, placeholder="Paste your log or text here...")
        
        # Actions
        if st.button(f"Run {mode} Analysis"):
            if mode == "JSON Key-Level":
                 run_key_level_analysis(creds, project_id, text_input, inspect_template, inspect_config, deidentify_template, deid_config, exception_keys, max_depth)
            else:
                 run_general_text_analysis(creds, project_id, text_input, inspect_template, inspect_config, deidentify_template, deid_config)

        
def run_general_text_analysis(creds, project_id, text_input, inspect_template, inspect_config, deidentify_template, deid_config):
    if not text_input:
        st.warning("Please enter some text to inspect.")
        return
    
    try:
        dlp_client = dlp_v2.DlpServiceClient(credentials=creds)
        parent = f"projects/{project_id}"
        item = {"value": text_input}
        
        # Prepare Inspect Kwargs
        inspect_kwargs = {}
        if inspect_template:
            inspect_kwargs["inspect_template_name"] = inspect_template
        else:
            inspect_kwargs["inspect_config"] = inspect_config

        with st.spinner("Inspecting..."):
            response = dlp_client.inspect_content(
                request={"parent": parent, "item": item, **inspect_kwargs}
            )

        # Prepare De-identify Kwargs
        deid_kwargs = {}
        if deidentify_template:
            deid_kwargs["deidentify_template_name"] = deidentify_template
        else:
             deid_kwargs["deidentify_config"] = deid_config
        
        with st.spinner("De-identifying..."):
            deid_response = dlp_client.deidentify_content(
                request={
                    "parent": parent,
                    "item": item,
                    **deid_kwargs,
                    **inspect_kwargs
                }
            )

        # Display Results
        st.subheader("Full Inspection Findings")
        if response.result.findings:
            findings_data = []
            for finding in response.result.findings:
                findings_data.append({
                    "Info Type": finding.info_type.name,
                    "Likelihood": finding.likelihood.name,
                    "Quote": finding.quote,
                })
            st.dataframe(findings_data, use_container_width=True)
        else:
            st.success("No findings detected.")
        
        st.subheader("De-identified Content")
        st.code(deid_response.item.value, language="json" if text_input.strip().startswith("{") else "text")

    except Exception as e:
        st.error(f"Error calling DLP API: {e}")

def run_key_level_analysis(creds, project_id, text_input, inspect_template, inspect_config, deidentify_template, deid_config, exception_keys, max_depth):
    try:
        data = json.loads(text_input)
    except json.JSONDecodeError:
        st.error("Input is not valid JSON. Key-Level Analysis requires JSON input.")
        return

    dlp_client = dlp_v2.DlpServiceClient(credentials=creds)
    parent = f"projects/{project_id}"
    
    # Flatten/Walk JSON
    flat_data = flatten_json(data, max_depth if max_depth > 0 else None)
    
    results = []
    
    # Progress Bar
    progress_bar = st.progress(0)
    total_items = len(flat_data)
    
    for i, (key, value) in enumerate(flat_data.items()):
        # Check Exception
        # We check if the last part of the key (the actual field name) is in exception list
        field_name = key.split(".")[-1]
        
        status = "Inspected"
        findings_summary = "None"
        redacted_value = ""
        
        if field_name in exception_keys:
            status = "Skipped (Exception)"
        elif not isinstance(value, str):
             status = "Skipped (Non-String)"
        else:
            # Inspect
            try:
                item = {"value": value}
                inspect_kwargs = {}
                if inspect_template:
                    inspect_kwargs["inspect_template_name"] = inspect_template
                else:
                    inspect_kwargs["inspect_config"] = inspect_config
                
                response = dlp_client.inspect_content(
                    request={"parent": parent, "item": item, **inspect_kwargs}
                )
                
                if response.result.findings:
                    findings = [f.info_type.name for f in response.result.findings]
                    findings_summary = ", ".join(set(findings))
                    status = "Findings Detected"
                    
                    # De-identify Only if Findings Detected
                    
                    # Prepare De-identify Kwargs
                    deid_kwargs = {}
                    if deidentify_template:
                        deid_kwargs["deidentify_template_name"] = deidentify_template
                    else:
                        deid_kwargs["deidentify_config"] = deid_config
                    
                    deid_response = dlp_client.deidentify_content(
                        request={
                            "parent": parent,
                            "item": item,
                            **deid_kwargs,
                            **inspect_kwargs
                        }
                    )
                    redacted_value = deid_response.item.value

            except Exception as e:
                status = f"Error: {str(e)}"
        
        row = {
            "Key": key,
            "Value": str(value)[:100] + "..." if len(str(value)) > 100 else value,
            "Status": status,
            "Findings": findings_summary
        }
        if redacted_value:
             row["Redacted Value"] = redacted_value
             
        results.append(row)
        progress_bar.progress((i + 1) / total_items)
        
    progress_bar.empty()
    
    st.subheader("Key-Level Analysis Report")
    df = pd.DataFrame(results)
    st.dataframe(df, use_container_width=True)

def flatten_json(y, max_depth=None):
    out = {}
    def flatten(x, name='', depth=0):
        # Stop Recursion if max_depth reached
        if max_depth is not None and depth >= max_depth:
            key = name[:-1] if name.endswith('.') else name
            if isinstance(x, (dict, list)):
                out[key] = json.dumps(x)
            else:
                out[key] = x
            return

        if type(x) is dict:
            for a in x:
                flatten(x[a], name + a + '.', depth + 1)
        elif type(x) is list:
            for i, a in enumerate(x):
                flatten(a, name + str(i) + '.', depth + 1)
        else:
            out[name[:-1]] = x
    flatten(y)
    return out
