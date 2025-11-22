import streamlit as st
import os
import json
import xml.etree.ElementTree as ET
import pandas as pd
from modules import linter  # To reuse export_and_extract_agent

def validate_ssml(text):
    """
    Validates SSML text using XML parsing.
    Returns (is_valid, error_message).
    """
    try:
        # SSML must have a root element. If it's just text with some tags, 
        # it might not be valid XML without a root.
        # However, DFCX usually expects <speak>...</speak> for SSML.
        # If it doesn't start with <speak>, it might be treated as plain text 
        # by some parsers, but here we are specifically looking for SSML issues.
        
        # If it looks like SSML (starts with <speak>), we parse it.
        if text.strip().startswith("<speak>"):
            ET.fromstring(text)
            return True, None
        else:
            # If it doesn't start with <speak>, it might just be text. 
            # But if it contains tags, it might be malformed SSML.
            # For now, let's only validate if it starts with <speak>.
            # Or if the user wants to check for *any* tags in plain text?
            # The requirement says "checking the agent response for SSML issues".
            # Let's assume if it has <speak> it must be valid XML.
            return True, None 
            
    except ET.ParseError as e:
        return False, str(e)
    except Exception as e:
        return False, str(e)

def find_ssml_in_fulfillment(fulfillment, path_prefix=""):
    """
    Recursively finds SSML in fulfillment objects.
    Yields (path, text, is_ssml).
    """
    if not fulfillment:
        return

    for msg_idx, msg in enumerate(fulfillment.get("messages", [])):
        # Check text
        if "text" in msg and "text" in msg["text"]:
            for text_idx, text in enumerate(msg["text"]["text"]):
                if "<speak>" in text: # Simple heuristic to identify potential SSML
                    yield f"{path_prefix}.messages[{msg_idx}].text.text[{text_idx}]", text, True
        
        # Check outputAudioText (SSML)
        if "outputAudioText" in msg and "ssml" in msg["outputAudioText"]:
            yield f"{path_prefix}.messages[{msg_idx}].outputAudioText.ssml", msg["outputAudioText"]["ssml"], True

def process_agent_files(temp_dir):
    """
    Walks through the agent files and validates SSML.
    Returns a list of issues.
    """
    issues = []
    flows_dir = os.path.join(temp_dir, "flows")
    
    if not os.path.exists(flows_dir):
        return issues

    # Walk through flows
    for flow_name in os.listdir(flows_dir):
        flow_path = os.path.join(flows_dir, flow_name)
        if not os.path.isdir(flow_path):
            continue
            
        # 1. Flow Definition
        flow_file = os.path.join(flow_path, f"{flow_name}.json")
        if os.path.exists(flow_file):
            with open(flow_file, "r") as f:
                flow_data = json.load(f)
                
            # Check event handlers
            for idx, handler in enumerate(flow_data.get("eventHandlers", [])):
                for path, text, _ in find_ssml_in_fulfillment(handler.get("triggerFulfillment"), f"Flow({flow_name}).eventHandlers[{idx}]"):
                    is_valid, err = validate_ssml(text)
                    if not is_valid:
                        issues.append({"Location": path, "Error": err, "Snippet": text[:100]})

            # Check transition routes
            for idx, route in enumerate(flow_data.get("transitionRoutes", [])):
                for path, text, _ in find_ssml_in_fulfillment(route.get("triggerFulfillment"), f"Flow({flow_name}).transitionRoutes[{idx}]"):
                    is_valid, err = validate_ssml(text)
                    if not is_valid:
                        issues.append({"Location": path, "Error": err, "Snippet": text[:100]})
                        
        # 2. Pages
        pages_dir = os.path.join(flow_path, "pages")
        if os.path.exists(pages_dir):
            for page_file in os.listdir(pages_dir):
                if not page_file.endswith(".json"):
                    continue
                
                with open(os.path.join(pages_dir, page_file), "r") as f:
                    page_data = json.load(f)
                    page_name = page_data.get("displayName", page_file)
                    
                # Entry fulfillment
                for path, text, _ in find_ssml_in_fulfillment(page_data.get("entryFulfillment"), f"Flow({flow_name}).Page({page_name}).entryFulfillment"):
                    is_valid, err = validate_ssml(text)
                    if not is_valid:
                        issues.append({"Location": path, "Error": err, "Snippet": text[:100]})

                # Form
                if "form" in page_data:
                    form = page_data["form"]
                    for param_idx, param in enumerate(form.get("parameters", [])):
                        fill_behavior = param.get("fillBehavior", {})
                        
                        # Initial prompt
                        for path, text, _ in find_ssml_in_fulfillment(fill_behavior.get("initialPromptFulfillment"), f"Flow({flow_name}).Page({page_name}).Form.Param[{param_idx}].initialPrompt"):
                            is_valid, err = validate_ssml(text)
                            if not is_valid:
                                issues.append({"Location": path, "Error": err, "Snippet": text[:100]})
                                
                        # Reprompt event handlers
                        for handler_idx, handler in enumerate(fill_behavior.get("repromptEventHandlers", [])):
                             for path, text, _ in find_ssml_in_fulfillment(handler.get("triggerFulfillment"), f"Flow({flow_name}).Page({page_name}).Form.Param[{param_idx}].reprompt[{handler_idx}]"):
                                is_valid, err = validate_ssml(text)
                                if not is_valid:
                                    issues.append({"Location": path, "Error": err, "Snippet": text[:100]})

                # Transition routes
                for idx, route in enumerate(page_data.get("transitionRoutes", [])):
                    for path, text, _ in find_ssml_in_fulfillment(route.get("triggerFulfillment"), f"Flow({flow_name}).Page({page_name}).transitionRoutes[{idx}]"):
                        is_valid, err = validate_ssml(text)
                        if not is_valid:
                            issues.append({"Location": path, "Error": err, "Snippet": text[:100]})

                # Event handlers
                for idx, handler in enumerate(page_data.get("eventHandlers", [])):
                    for path, text, _ in find_ssml_in_fulfillment(handler.get("triggerFulfillment"), f"Flow({flow_name}).Page({page_name}).eventHandlers[{idx}]"):
                        is_valid, err = validate_ssml(text)
                        if not is_valid:
                            issues.append({"Location": path, "Error": err, "Snippet": text[:100]})

        # 3. Route Groups (Transition Route Groups)
        # These are reusable groups of routes, but they are defined in separate files?
        # Actually, in the export structure, they are usually in `transitionRouteGroups` folder inside flow.
        trg_dir = os.path.join(flow_path, "transitionRouteGroups")
        if os.path.exists(trg_dir):
            for trg_file in os.listdir(trg_dir):
                if not trg_file.endswith(".json"):
                    continue
                
                with open(os.path.join(trg_dir, trg_file), "r") as f:
                    trg_data = json.load(f)
                    trg_name = trg_data.get("displayName", trg_file)
                    
                for idx, route in enumerate(trg_data.get("transitionRoutes", [])):
                    for path, text, _ in find_ssml_in_fulfillment(route.get("triggerFulfillment"), f"Flow({flow_name}).TRG({trg_name}).transitionRoutes[{idx}]"):
                        is_valid, err = validate_ssml(text)
                        if not is_valid:
                            issues.append({"Location": path, "Error": err, "Snippet": text[:100]})

    return issues

def render_ssml_linter(credentials, agent_details):
    st.markdown("Validate SSML tags in agent responses to ensure XML correctness and prevent runtime errors.")
    
    if st.button("Run SSML Validation"):
        try:
            agent_name = agent_details['name']
            
            # Reuse export logic
            temp_dir = linter.export_and_extract_agent(credentials, agent_details)
            st.success("Agent exported successfully.")
            
            with st.spinner("Validating SSML..."):
                issues = process_agent_files(temp_dir)
                st.session_state['ssml_issues'] = issues
                
            # Cleanup
            import shutil
            shutil.rmtree(temp_dir)
            
        except Exception as e:
            st.error(f"Error: {e}")
            st.exception(e)

    if 'ssml_issues' in st.session_state:
        issues = st.session_state['ssml_issues']
        if issues:
            st.error(f"Found {len(issues)} SSML issues!")
            df = pd.DataFrame(issues)
            
            # Extract Flow from Location
            # Location format: Flow(Flow Name).Page(Page Name)...
            # We can use regex or simple string splitting if consistent
            import re
            def extract_flow(loc):
                match = re.search(r"Flow\((.*?)\)", loc)
                return match.group(1) if match else "Unknown"
            
            df['Flow'] = df['Location'].apply(extract_flow)
            
            # Reorder columns to put Flow first
            cols = ['Flow'] + [c for c in df.columns if c != 'Flow']
            df = df[cols]
            
            # Filter by Flow
            all_flows = sorted(df['Flow'].unique())
            selected_flows = st.multiselect("Filter by Flow", options=all_flows, default=all_flows)
            
            if selected_flows:
                filtered_df = df[df['Flow'].isin(selected_flows)]
                st.dataframe(filtered_df, width='stretch')
            else:
                st.info("Select flows to view issues.")
                
        else:
            st.success("No SSML issues found! (Checked all <speak> blocks)")
