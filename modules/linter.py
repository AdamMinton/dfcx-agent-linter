import streamlit as st
import os
import tempfile
import zipfile
import shutil
from google.cloud import dialogflowcx_v3
from cxlint.cxlint import CxLint
import io
from contextlib import redirect_stdout
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

def export_and_extract_agent(credentials, agent_name):
    """Exports the agent from DFCX and extracts it to a temp directory."""
    client = dialogflowcx_v3.AgentsClient(credentials=credentials)
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
    st.subheader(f"Linting Agent: {agent_details['display_name']}")
    
    if st.button("Run CXLint"):
        try:
            agent_name = agent_details['name']
            
            # 1. Export Agent
            temp_dir = export_and_extract_agent(credentials, agent_name)
            st.success(f"Agent exported to temporary directory.")
            
            # 2. Run CXLint
            with st.spinner("Running cxlint..."):
                # Capture output
                output_file = os.path.join(temp_dir, "cxlint_report.txt")
                
                # Initialize CxLint
                # We might need to suppress stdout if it prints directly
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
                    
                    st.text_area("Lint Report", report_content, height=400)
                else:
                    st.warning("No report file generated. Check logs.")
                    
            # Cleanup
            shutil.rmtree(temp_dir)
            
        except Exception as e:
            st.error(f"Error running cxlint: {e}")
            st.exception(e)
