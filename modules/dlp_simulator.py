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
            "taskList", "ProvidedContactTn", "goal", "ProvidedIDMatchedToBill",
            # Timestamps
            "timestamp", "time", "date", "createTime", "updateTime", "startTime", "endTime",
            "receiveTimestamp", "sentTimestamp", "publishTime",
            # Metadata
            "labels", "name", "displayName", "blob_release_version",
            "completeTime", "flowState", "pageState", "logName",
            "insertId", "advancedSettings"
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
                 df = run_key_level_analysis(creds, project_id, text_input, inspect_template, inspect_config, deidentify_template, deid_config, exception_keys, max_depth)
                 st.session_state['dlp_key_results'] = df
                 st.session_state['dlp_active_mode'] = "JSON Key-Level"
            else:
                 # General Text analysis still renders directly
                 run_general_text_analysis(creds, project_id, text_input, inspect_template, inspect_config, deidentify_template, deid_config)
                 st.session_state['dlp_active_mode'] = "General Text" # Clear key results implicitly by mode switch

        # Render Key-Level Results if available and active
        if st.session_state.get('dlp_active_mode') == "JSON Key-Level" and 'dlp_key_results' in st.session_state:
            res_df = st.session_state['dlp_key_results']
            st.subheader("Key-Level Analysis Report")
            
            # Status Filter
            if not res_df.empty and "Status" in res_df.columns:
                all_statuses = sorted(res_df["Status"].astype(str).unique().tolist())
                # Use a key for the widget to ensure it doesn't lose state easily
                selected_statuses = st.multiselect("Filter by Status", options=all_statuses, default=all_statuses, key="dlp_status_filter")
                
                if selected_statuses:
                    filtered_df = res_df[res_df["Status"].isin(selected_statuses)]
                    st.dataframe(filtered_df, width="stretch")
                else:
                    st.info("No records match the selected filters.")
            else:
                st.dataframe(res_df, width="stretch")

        
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
            st.dataframe(findings_data, width="stretch")
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
    
    # Prepare for Batch Inspection
    valid_rows = [] # List of {'key': k, 'value': v, 'original_index': i}
    results = [None] * len(flat_data) # Pre-allocate results with None
    
    for i, (key, value) in enumerate(flat_data.items()):
        # Check Exception
        key_parts = key.split(".")
        is_exception = any(part in exception_keys for part in key_parts)
        
        status = "Inspected"
        findings_summary = "None"
        redacted_value = ""
        
        row_result = {
            "Key": key,
            "Value": str(value), 
            "Length": len(str(value)),
            "Status": status,
            "Findings": findings_summary
        }

        if is_exception:
            row_result["Status"] = "Skipped (Exception)"
            results[i] = row_result
        elif not isinstance(value, str):
             row_result["Status"] = "Skipped (Non-String)"
             results[i] = row_result
        else:
             # Add to batch
             valid_rows.append({
                 "original_index": i,
                 "key": key,
                 "value": str(value)
             })
             # Placeholder in results, will be updated after batch processing
             results[i] = row_result

    # Batch Execution
    if valid_rows:
        try:
            # Construct Table
            headers = [{"name": "value"}]
            # dlp_v2.Table expects rows of specific structure
            rows = [{"values": [{"string_value": r['value']}]} for r in valid_rows]
            
            table_item = {"table": {"headers": headers, "rows": rows}}
            
            # Common Kwargs
            inspect_kwargs = {}
            if inspect_template:
                inspect_kwargs["inspect_template_name"] = inspect_template
            else:
                inspect_kwargs["inspect_config"] = inspect_config

            deid_kwargs = {}
            if deidentify_template:
                deid_kwargs["deidentify_template_name"] = deidentify_template
            else:
                deid_kwargs["deidentify_config"] = deid_config

            # 1. Inspect
            with st.spinner(f"Inspecting {len(valid_rows)} items in batch..."):
                inspect_response = dlp_client.inspect_content(
                    request={"parent": parent, "item": table_item, **inspect_kwargs}
                )

            # Map Findings
            # Findings location: content_locations[0].record_location.table_location.row_index
            findings_map = {} # row_index -> set of findings
            
            if inspect_response.result.findings:
                for f in inspect_response.result.findings:
                    # Row index in the batch table
                    row_idx = f.location.content_locations[0].record_location.table_location.row_index
                    if row_idx not in findings_map:
                        findings_map[row_idx] = set()
                    findings_map[row_idx].add(f.info_type.name)

            # 2. De-identify (Batch)
            # We de-identify the entire table. It's efficient and simpler.
            with st.spinner(f"De-identifying {len(valid_rows)} items in batch..."):
                deid_response = dlp_client.deidentify_content(
                    request={
                        "parent": parent,
                        "item": table_item,
                        **deid_kwargs,
                        **inspect_kwargs
                    }
                )
            
            transformed_rows = deid_response.item.table.rows

            # Update Results
            for batch_idx, r in enumerate(valid_rows):
                orig_idx = r['original_index']
                
                # Findings
                if batch_idx in findings_map:
                    results[orig_idx]["Status"] = "Findings Detected"
                    results[orig_idx]["Findings"] = ", ".join(sorted(findings_map[batch_idx]))
                    
                    # Redacted Value
                    # For simple masking, the de-identified value is in the corresponding row/col
                    if batch_idx < len(transformed_rows):
                         val = transformed_rows[batch_idx].values[0].string_value
                         results[orig_idx]["Redacted Value"] = val
                else:
                    results[orig_idx]["Status"] = "Inspected"
                    # Optional: We could show the value even if no findings, but usually user cares when things change.
                    # If the user wants to see "Inspected" values unchanged, they are already in "Value" col.
                    # If we used a transformation that changes things even without infoTypes (e.g. bucketing), 
                    # we would want to show it. But usually redaction is triggered by findings.
                    # For consistency with previous behavior (redacted only if findings), we leave it empty.
                    pass

        except Exception as e:
            st.error(f"Error during batch processing: {e}")
            # Fallback or just show error for all valid rows
            for r in valid_rows:
                results[r['original_index']]["Status"] = f"Batch Error: {str(e)}"
    
    # progress_bar references removed as we use st.spinner now
    
    # Return results for rendering
    return pd.DataFrame(results)

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
