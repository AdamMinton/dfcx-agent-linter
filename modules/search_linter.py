import streamlit as st
import pandas as pd
import re
import os
import shutil
from modules import linter, graph_linter

class AgentSearcher:
    def __init__(self, agent_dir):
        self.graph = graph_linter.OfflineFlowGraph(agent_dir)
        
    def search(self, query, regex=False, ignore_case=True, scope="All"):
        results = []
        
        flags = re.IGNORECASE if ignore_case else 0
        if not regex:
            query = re.escape(query)
            
        pattern = re.compile(query, flags)
        
        for flow_id, flow_data in self.graph.flows.items():
            flow_name = flow_data.get("displayName", flow_id)
            
            # Search Flow Transition Routes
            if scope in ["All", "Routes"]:
                for route in flow_data.get("transitionRoutes", []):
                    self._check_route(route, pattern, flow_name, "Start", "Flow Transition Route", results)
                    
            # Search Flow Event Handlers
            if scope in ["All", "Event Handlers"]:
                for handler in flow_data.get("eventHandlers", []):
                    self._check_event_handler(handler, pattern, flow_name, "Start", "Flow Event Handler", results)
            
            # Search Pages
            for page_id, page_data in self.graph.pages.get(flow_id, {}).items():
                page_name = page_data.get("displayName", page_id)
                
                # Entry Fulfillment
                if scope in ["All", "Fulfillment"]:
                    self._check_fulfillment(page_data.get("entryFulfillment"), pattern, flow_name, page_name, "Entry Fulfillment", results)
                
                # Form
                if scope in ["All", "Parameters"]:
                    if "form" in page_data:
                        for param in page_data["form"].get("parameters", []):
                            p_name = param.get("displayName", "Unknown")
                            # Check initial prompt
                            self._check_fulfillment(param.get("fillBehavior", {}).get("initialPromptFulfillment"), pattern, flow_name, page_name, f"Parameter {p_name} Initial Prompt", results)
                            # Check reprompts
                            for h in param.get("fillBehavior", {}).get("repromptEventHandlers", []):
                                self._check_fulfillment(h.get("triggerFulfillment"), pattern, flow_name, page_name, f"Parameter {p_name} Reprompt", results)
                
                # Page Routes
                if scope in ["All", "Routes"]:
                    for route in page_data.get("transitionRoutes", []):
                        self._check_route(route, pattern, flow_name, page_name, "Page Transition Route", results)
                
                # Page Event Handlers
                if scope in ["All", "Event Handlers"]:
                    for handler in page_data.get("eventHandlers", []):
                        self._check_event_handler(handler, pattern, flow_name, page_name, "Page Event Handler", results)

            # Search TRGs
            if scope in ["All", "Routes"]:
                for trg_id, trg_data in self.graph.trgs.get(flow_id, {}).items():
                    trg_name = trg_data.get("displayName", trg_id)
                    for route in trg_data.get("transitionRoutes", []):
                        self._check_route(route, pattern, flow_name, f"TRG: {trg_name}", "TRG Route", results)

        return pd.DataFrame(results)

    def _check_fulfillment(self, fulfillment, pattern, flow, page, location, results):
        if not fulfillment: return
        
        # Messages
        for msg in fulfillment.get("messages", []):
            # Text
            if "text" in msg:
                for t in msg["text"].get("text", []):
                    if pattern.search(t):
                        results.append({
                            "Flow": flow, "Page": page, "Location": location, "Type": "Text", "Match": t, "Context": "Message"
                        })
            # Payload
            if "payload" in msg:
                payload_str = str(msg["payload"])
                if pattern.search(payload_str):
                     results.append({
                            "Flow": flow, "Page": page, "Location": location, "Type": "Payload", "Match": payload_str[:100], "Context": "Custom Payload"
                        })
        
        # Webhook
        if "webhook" in fulfillment:
            w = fulfillment["webhook"]
            if pattern.search(w):
                 results.append({
                            "Flow": flow, "Page": page, "Location": location, "Type": "Webhook", "Match": w, "Context": "Webhook Ref"
                        })
            
            # Tag
            if "tag" in fulfillment:
                t = fulfillment["tag"]
                if pattern.search(t):
                    results.append({
                            "Flow": flow, "Page": page, "Location": location, "Type": "Tag", "Match": t, "Context": "Webhook Tag"
                        })
        
        # Parameter Presets
        for preset in fulfillment.get("setParameterActions", []):
            p = preset.get("parameter", "")
            v = str(preset.get("value", ""))
            if pattern.search(p) or pattern.search(v):
                results.append({
                            "Flow": flow, "Page": page, "Location": location, "Type": "Parameter Preset", "Match": f"{p} = {v}", "Context": "Set Parameter"
                        })

    def _check_route(self, route, pattern, flow, page, location, results):
        # Condition
        cond = route.get("condition", "")
        if pattern.search(cond):
            results.append({
                "Flow": flow, "Page": page, "Location": location, "Type": "Condition", "Match": cond, "Context": "Route Condition"
            })
        
        # Intent
        intent = route.get("intent", "")
        if pattern.search(intent):
             results.append({
                "Flow": flow, "Page": page, "Location": location, "Type": "Intent", "Match": intent, "Context": "Route Intent"
            })
            
        # Target Page
        target_page = route.get("targetPage", "")
        if pattern.search(target_page):
             results.append({
                "Flow": flow, "Page": page, "Location": location, "Type": "Target Page", "Match": target_page, "Context": "Route Target"
            })

        # Target Flow
        target_flow = route.get("targetFlow", "")
        if pattern.search(target_flow):
             results.append({
                "Flow": flow, "Page": page, "Location": location, "Type": "Target Flow", "Match": target_flow, "Context": "Route Target"
            })
            
        # Trigger Fulfillment
        self._check_fulfillment(route.get("triggerFulfillment"), pattern, flow, page, location, results)

    def _check_event_handler(self, handler, pattern, flow, page, location, results):
        event = handler.get("event", "")
        if pattern.search(event):
             results.append({
                "Flow": flow, "Page": page, "Location": location, "Type": "Event", "Match": event, "Context": "Event Handler"
            })
        
        self._check_fulfillment(handler.get("triggerFulfillment"), pattern, flow, page, location, results)


def render_search_linter(credentials, agent_details):
    st.markdown("Search for specific strings or patterns across the agent's flows, pages, routes, and fulfillment.")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        query = st.text_input("Search Query")
    with col2:
        scope = st.selectbox("Scope", ["All", "Fulfillment", "Routes", "Parameters", "Event Handlers"])
        
    c1, c2 = st.columns(2)
    with c1:
        regex = st.checkbox("Regex Search")
    with c2:
        ignore_case = st.checkbox("Ignore Case", value=True)
        
    if st.button("Search"):
        if not query:
            st.warning("Please enter a search query.")
            return
            
        try:
            agent_name = agent_details['name']
            temp_dir = linter.export_and_extract_agent(credentials, agent_name)
            
            with st.spinner("Searching..."):
                searcher = AgentSearcher(temp_dir)
                df = searcher.search(query, regex=regex, ignore_case=ignore_case, scope=scope)
                
            if not df.empty:
                st.success(f"Found {len(df)} matches.")
                st.dataframe(df, use_container_width=True)
            else:
                st.info("No matches found.")
                
            shutil.rmtree(temp_dir)
            
        except Exception as e:
            st.error(f"Error: {e}")
            st.exception(e)
