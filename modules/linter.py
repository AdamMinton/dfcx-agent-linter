import streamlit as st
import os
import tempfile
import zipfile
import shutil
from google.cloud import dialogflowcx_v3
from cxlint.cxlint import CxLint
import io
from contextlib import redirect_stdout
import pandas as pd
from rich.markup import escape
from cxlint.rules.logger import RulesLogger
# Monkeypatch generic_logger to escape markup in display names
# This is necessary because cxlint uses the 'rich' library for logging, which interprets
# certain characters (like brackets) as markup tags. DFCX display names often contain
# these characters, leading to MarkupError if not escaped.

# 1. Check if we already patched it and restore the original if so
# This prevents recursion errors and ensures we always patch the base method
if hasattr(RulesLogger, '_original_generic_logger'):
    RulesLogger.generic_logger = RulesLogger._original_generic_logger

# 2. Save the (now guaranteed original) logger
RulesLogger._original_generic_logger = RulesLogger.generic_logger

def patched_generic_logger(self, resource, rule, message):
    """
    Patched logger that escapes display names before logging to prevent Rich MarkupErrors.
    It also wraps the logging call in a try/except block as a fail-safe.
    """
    # Attributes that might contain special characters needing escaping
    attrs_to_escape = [
        'entity_type_display_name',
        'flow_display_name',
        'page_display_name',
        'intent_display_name',
        'test_case_display_name',
        'webhook_display_name'
    ]
    
    for attr in attrs_to_escape:
        if hasattr(resource, attr):
            try:
                val = getattr(resource, attr)
                if val is not None and isinstance(val, str):
                    # Escape the value to be safe for Rich
                    escaped_val = escape(val)
                    setattr(resource, attr, escaped_val)
            except Exception:
                # If escaping fails, we just continue with the original value
                pass
    
    # Call the original logger stored on the class
    try:
        RulesLogger._original_generic_logger(self, resource, rule, message)
    except Exception as e:
        # If rich fails to render (e.g. MarkupError), fallback to simple print
        # We reconstruct a simple message without links to avoid crashing the app
        print(f"Rich logging failed: {e}")
        print(f"{rule} : {message} (Resource: {getattr(resource, 'display_name', 'Unknown')})")

RulesLogger.generic_logger = patched_generic_logger

# Monkeypatch EntityTypeRules.entity_type_naming_convention to fix UnboundLocalError
# The original code checks 'if not res:' but 'res' is only defined if 'etype.naming_pattern' is truthy.
from cxlint.rules.entity_types import EntityTypeRules
import re
from cxlint.resources.types import Resource

def patched_entity_type_naming_convention(self, etype, stats):
    """Check that the Entity Type display name conform to given pattern."""
    rule = "R015: Naming Conventions"
    
    # Initialize res to True (pass) by default if no pattern is provided
    res = True

    if etype.naming_pattern:
        res = re.search(etype.naming_pattern, etype.display_name)
        stats.total_inspected += 1

    if not res:
        resource = Resource()
        resource.agent_id = etype.agent_id
        resource.entity_type_display_name = etype.display_name
        resource.entity_type_id = etype.resource_id
        resource.resource_type = "entity_type"

        message = ": Entity Type Display Name does not meet the specified"\
            f" Convention : {etype.naming_pattern}"
        stats.total_issues += 1

        self.log.generic_logger(resource, rule, message)

    return stats

EntityTypeRules.entity_type_naming_convention = patched_entity_type_naming_convention

# Monkeypatch TestCaseRules.test_case_naming_convention to fix UnboundLocalError
# Same issue as above: 'res' is used before assignment if 'tc.naming_pattern' is falsy.
from cxlint.rules.test_cases import TestCaseRules

def patched_test_case_naming_convention(self, tc, stats):
    """Check Test Case Display Name conforms to naming conventions."""
    rule = "R015: Naming Conventions"

    # Initialize res to True (pass) by default
    res = True

    if tc.naming_pattern:
        res = re.search(tc.naming_pattern, tc.display_name)
        stats.total_inspected += 1

    if not res:
        resource = Resource()
        resource.agent_id = tc.agent_id
        resource.test_case_display_name = tc.display_name
        resource.test_case_id = tc.resource_id
        resource.resource_type = "test_case"

        message = ": Test Case Display Name does not meet the specified"\
            f" Convention : {tc.naming_pattern}"
        stats.total_issues += 1

        self.log.generic_logger(resource, rule, message)

    return stats

TestCaseRules.test_case_naming_convention = patched_test_case_naming_convention

# Monkeypatch WebhookRules.webhook_naming_conventions to fix UnboundLocalError
from cxlint.rules.webhooks import WebhookRules

def patched_webhook_naming_conventions(self, webhook, stats):
    """Check Webhook Display Name conforms to naming conventions."""
    rule = "R015: Naming Conventions"

    # Initialize res to True (pass) by default
    res = True

    if webhook.naming_pattern:
        res = re.search(webhook.naming_pattern, webhook.display_name)
        stats.total_inspected += 1

    if not res:
        resource = Resource()
        resource.agent_id = webhook.agent_id
        resource.webhook_display_name = webhook.display_name
        resource.webhook_id = webhook.resource_id
        resource.resource_type = "webhook"

        message = ": Webhook Display Name does not meet the specified"\
            f" Convention : {webhook.naming_pattern}"
        stats.total_issues += 1

        self.log.generic_logger(resource, rule, message)

    return stats

WebhookRules.webhook_naming_conventions = patched_webhook_naming_conventions

# Proactively patch FlowRules.flow_naming_convention just in case
from cxlint.rules.flows import FlowRules

def patched_flow_naming_convention(self, flow, stats):
    """Check Flow Display Name conforms to naming conventions."""
    rule = "R015: Naming Conventions"

    # Initialize res to True (pass) by default
    res = True

    if flow.naming_pattern:
        res = re.search(flow.naming_pattern, flow.display_name)
        stats.total_inspected += 1

    if not res:
        resource = Resource()
        resource.agent_id = flow.agent_id
        resource.flow_display_name = flow.display_name
        resource.flow_id = flow.resource_id
        resource.resource_type = "flow"

        message = ": Flow Display Name does not meet the specified"\
            f" Convention : {flow.naming_pattern}"
        stats.total_issues += 1

        self.log.generic_logger(resource, rule, message)

    return stats

FlowRules.flow_naming_convention = patched_flow_naming_convention

# Proactively patch PageRules.page_naming_convention just in case
from cxlint.rules.pages import PageRules

def patched_page_naming_convention(self, page, stats):
    """Check Page Display Name conforms to naming conventions."""
    rule = "R015: Naming Conventions"

    # Initialize res to True (pass) by default
    res = True

    if page.naming_pattern:
        res = re.search(page.naming_pattern, page.display_name)
        stats.total_inspected += 1

    if not res:
        resource = Resource()
        resource.agent_id = page.agent_id
        resource.flow_display_name = page.flow_display_name
        resource.page_display_name = page.display_name
        resource.page_id = page.resource_id
        resource.resource_type = "page"

        message = ": Page Display Name does not meet the specified"\
            f" Convention : {page.naming_pattern}"
        stats.total_issues += 1

        self.log.generic_logger(resource, rule, message)

    return stats

PageRules.page_naming_convention = patched_page_naming_convention

def parse_cxlint_report(report_content):
    """
    Parses the raw text report from CXLint into structured DataFrames.
    Returns a dictionary of DataFrames: {'Flows': df, 'Entity Types': df, 'Intents': df, 'Test Cases': df}
    """
    data = {
        'Flows': [],
        'Entity Types': [],
        'Intents': [],
        'Test Cases': []
    }
    
    current_section = None
    lines = report_content.split('\n')
    
    # Regex patterns
    # Example: R012: Unused Pages : Plans & Features : _Eligibility Check (Single Device)
    # Format seems to be: RuleID: Description : Flow : Page (for flows)
    # But it varies by section.
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        if "Begin Flows Directory Linter" in line:
            current_section = 'Flows'
            continue
        elif "Begin Entity Types Directory Linter" in line:
            current_section = 'Entity Types'
            continue
        elif "Begin Intents Directory Linter" in line:
            current_section = 'Intents'
            continue
        elif "Begin Test Cases Directory Linter" in line:
            current_section = 'Test Cases'
            continue
        elif "Linting Agent" in line or "issues found out of" in line or "rated at" in line or "Flow:" in line:
            # Skip headers/footers/summaries
            # Note: "Flow: Default Start Flow" lines are just separators/headers in the text output, 
            # but the actual issues have the flow name in them usually.
            continue
            
        if current_section and line.startswith('R'):
            parts = [p.strip() for p in line.split(':', 3)]
            # parts[0] = RuleID (e.g. R012)
            # parts[1] = Description (e.g. Unused Pages)
            # parts[2] = Resource Name / Flow (e.g. Plans & Features)
            # parts[3] = Details / Page (e.g. _Eligibility Check...)
            
            if len(parts) >= 3:
                rule_id = parts[0]
                description = parts[1]
                
                if current_section == 'Flows':
                    # R012: Unused Pages : Plans & Features : _Eligibility Check
                    # Flow is parts[2], Page/Details is parts[3] if exists
                    flow = parts[2]
                    details = parts[3] if len(parts) > 3 else ""
                    data['Flows'].append({
                        'Rule ID': rule_id,
                        'Description': description,
                        'Flow': flow,
                        'Details': details,
                        'Original': line
                    })
                    
                elif current_section == 'Entity Types':
                    # R009: Yes/No Entities Present in Agent : confirmation_yes_no : en : Entity : yes
                    # This one splits differently.
                    # Let's just capture the raw parts for now or try to be smart.
                    # parts[2] is usually the Entity Type name
                    entity_type = parts[2]
                    details = parts[3] if len(parts) > 3 else ""
                    data['Entity Types'].append({
                        'Rule ID': rule_id,
                        'Description': description,
                        'Entity Type': entity_type,
                        'Details': details,
                        'Original': line
                    })
                    
                elif current_section == 'Intents':
                    # R005: Intent Does Not Have Minimum Training Phrases. : pmt_consolidate_nfl_pmts : en : (17 / 20)
                    intent = parts[2]
                    details = parts[3] if len(parts) > 3 else ""
                    data['Intents'].append({
                        'Rule ID': rule_id,
                        'Description': description,
                        'Intent': intent,
                        'Details': details,
                        'Original': line
                    })
                    
                elif current_section == 'Test Cases':
                    # R007: Explicit Training Phrase Not in Test Case : DEF.CCSMATRIX-1286... : [Utterance: ... | Intent: ...]
                    test_case = parts[2]
                    details = parts[3] if len(parts) > 3 else ""
                    data['Test Cases'].append({
                        'Rule ID': rule_id,
                        'Description': description,
                        'Test Case': test_case,
                        'Details': details,
                        'Original': line
                    })

    dfs = {}
    for section, rows in data.items():
        if rows:
            dfs[section] = pd.DataFrame(rows)
        else:
            dfs[section] = pd.DataFrame()
            
    return dfs

def export_and_extract_agent(credentials, agent_details):
    """Exports the agent from DFCX and extracts it to a temp directory."""
    agent_name = agent_details['name']
    location = agent_details['location']
    
    client_options = None
    if location != "global":
        api_endpoint = f"{location}-dialogflow.googleapis.com:443"
        client_options = {"api_endpoint": api_endpoint}
        
    client = dialogflowcx_v3.AgentsClient(credentials=credentials, client_options=client_options)
    request = dialogflowcx_v3.ExportAgentRequest(
        name=agent_name,
        data_format=dialogflowcx_v3.ExportAgentRequest.DataFormat.JSON_PACKAGE
    )
    
    with st.spinner("Exporting agent..."):
        operation = client.export_agent(request=request)
        response = operation.result()
        
    # The response contains the agent content as bytes
    agent_content = response.agent_content
    
    temp_dir = tempfile.mkdtemp()
    zip_path = os.path.join(temp_dir, "agent.zip")
    
    with open(zip_path, "wb") as f:
        f.write(agent_content)
        
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(temp_dir)
        
    return temp_dir

def render_linter(credentials, agent_details):
    """Renders the cxlint runner and results."""
    st.markdown("Run `cxlint` to identify common issues such as naming convention violations, missing training phrases, and more.")
    
    if st.button("Run CXLint"):
        try:
            agent_name = agent_details['name']
            
            # 1. Export Agent
            temp_dir = export_and_extract_agent(credentials, agent_details)
            st.success(f"Agent exported to temporary directory.")
            
            # 2. Run CXLint
            with st.spinner("Running cxlint..."):
                # Capture output
                output_file = os.path.join(temp_dir, "cxlint_report.txt")
                
                # Initialize CxLint
                linter = CxLint(
                    agent_id=agent_details['display_name'],
                    output_file=output_file,
                    verbose=True
                )
                
                # Run linting
                linter.lint_agent(temp_dir)
                
                # Read report
                if os.path.exists(output_file):
                    with open(output_file, "r") as f:
                        report_content = f.read()
                    
                    # Parse and display
                    dfs = parse_cxlint_report(report_content)
                    st.session_state['cxlint_results'] = dfs
                    st.session_state['cxlint_report_content'] = report_content
                    
                else:
                    st.warning("No report file generated. Check logs.")
                    
            # Cleanup
            shutil.rmtree(temp_dir)
            
        except Exception as e:
            st.error(f"Error running cxlint: {e}")
            st.exception(e)

    # Render results if they exist in session state
    if 'cxlint_results' in st.session_state:
        dfs = st.session_state['cxlint_results']
        report_content = st.session_state.get('cxlint_report_content', "")
        
        # Tabs for sections
        tabs = st.tabs(["Flows", "Entity Types", "Intents", "Test Cases", "Raw Report"])
        
        from modules import ui_utils
        
        with tabs[0]:
            ui_utils.render_dataframe_with_filter(dfs.get('Flows', pd.DataFrame()), title="Flow Issues")
                
        with tabs[1]:
            st.markdown("### Entity Type Issues")
            df_et = dfs.get('Entity Types', pd.DataFrame())
            if not df_et.empty:
                st.dataframe(df_et, width='stretch')
            else:
                st.success("No Entity Type issues found.")
                
        with tabs[2]:
            st.markdown("### Intent Issues")
            df_intents = dfs.get('Intents', pd.DataFrame())
            if not df_intents.empty:
                st.dataframe(df_intents, width='stretch')
            else:
                st.success("No Intent issues found.")
                
        with tabs[3]:
            st.markdown("### Test Case Issues")
            df_tc = dfs.get('Test Cases', pd.DataFrame())
            if not df_tc.empty:
                st.dataframe(df_tc, width='stretch')
            else:
                st.success("No Test Case issues found.")
                
        with tabs[4]:
            st.text_area("Raw Lint Report", report_content, height=400)
