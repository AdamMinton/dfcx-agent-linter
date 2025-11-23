import streamlit as st
import os
import json
import pandas as pd
from typing import Dict, List, Optional, Set, Tuple
from modules import linter
import shutil

class OfflineFlowGraph:
    def __init__(self, agent_dir: str):
        self.agent_dir = agent_dir
        self.flows = {} # flow_id -> flow_data
        self.pages = {} # flow_id -> {page_id -> page_data}
        self.trgs = {} # flow_id -> {trg_id -> trg_data}
        self.flow_name_map = {} # flow_name -> flow_id
        self.load_agent()

    def load_agent(self):
        flows_dir = os.path.join(self.agent_dir, "flows")
        if not os.path.exists(flows_dir):
            return

        for flow_name in os.listdir(flows_dir):
            flow_path = os.path.join(flows_dir, flow_name)
            if not os.path.isdir(flow_path):
                continue

            # Load Flow
            flow_file = os.path.join(flow_path, f"{flow_name}.json")
            if os.path.exists(flow_file):
                with open(flow_file, "r") as f:
                    flow_data = json.load(f)
                    flow_id = flow_data.get("name", flow_name) # Use name as ID if available, else dir name
                    self.flows[flow_id] = flow_data
                    self.flow_name_map[flow_data.get("displayName", flow_name)] = flow_id
                    self.pages[flow_id] = {}
                    self.trgs[flow_id] = {}

                    # Load Pages
                    pages_dir = os.path.join(flow_path, "pages")
                    if os.path.exists(pages_dir):
                        for page_file in os.listdir(pages_dir):
                            if page_file.endswith(".json"):
                                with open(os.path.join(pages_dir, page_file), "r") as pf:
                                    page_data = json.load(pf)
                                    page_id = page_data.get("name", page_file)
                                    self.pages[flow_id][page_id] = page_data

                    # Load TRGs
                    trgs_dir = os.path.join(flow_path, "transitionRouteGroups")
                    if os.path.exists(trgs_dir):
                        for trg_file in os.listdir(trgs_dir):
                            if trg_file.endswith(".json"):
                                with open(os.path.join(trgs_dir, trg_file), "r") as tf:
                                    trg_data = json.load(tf)
                                    trg_id = trg_data.get("name", trg_file)
                                    self.trgs[flow_id][trg_id] = trg_data

    def get_page_display_name(self, flow_id, page_id):
        if page_id == "Start":
            return "Start"
        if page_id in self.pages.get(flow_id, {}):
            return self.pages[flow_id][page_id].get("displayName", page_id)
        return page_id

    def find_reachable_pages(self, flow_id: str) -> Set[str]:
        """Finds all reachable pages in a flow starting from Start."""
        visited = set()
        queue = ["Start"]
        visited.add("Start")

        while queue:
            current_page_id = queue.pop(0)
            
            # Get transitions
            transitions = []
            if current_page_id == "Start":
                flow_data = self.flows.get(flow_id)
                if flow_data:
                    transitions.extend(flow_data.get("transitionRoutes", []))
                    # Add TRGs
                    for trg_ref in flow_data.get("transitionRouteGroups", []):
                        # trg_ref might be the ID or name, need to resolve if possible
                        # In JSON export, it's usually the full resource name
                        # We try to match it to our loaded TRGs
                        trg = self.resolve_trg(flow_id, trg_ref)
                        if trg:
                            transitions.extend(trg.get("transitionRoutes", []))
                    
                    # Event handlers can also transition
                    transitions.extend(flow_data.get("eventHandlers", []))

            elif current_page_id in self.pages.get(flow_id, {}):
                page_data = self.pages[flow_id][current_page_id]
                transitions.extend(page_data.get("transitionRoutes", []))
                for trg_ref in page_data.get("transitionRouteGroups", []):
                    trg = self.resolve_trg(flow_id, trg_ref)
                    if trg:
                        transitions.extend(trg.get("transitionRoutes", []))
                transitions.extend(page_data.get("eventHandlers", []))

            for route in transitions:
                target_page = route.get("targetPage")
                target_flow = route.get("targetFlow")
                
                if target_page:
                    # Resolve target page ID
                    # In JSON, it's usually the full resource name. 
                    # We need to extract the last part or match it.
                    # For simplicity, let's assume we can match by suffix or it's the full name.
                    resolved_page_id = self.resolve_page_id(flow_id, target_page)
                    if resolved_page_id and resolved_page_id not in visited:
                        visited.add(resolved_page_id)
                        queue.append(resolved_page_id)
        
        return visited

    def resolve_trg(self, flow_id, trg_ref):
        # trg_ref is likely a full resource path
        # We check if any of our loaded TRGs match
        for trg_id, trg_data in self.trgs.get(flow_id, {}).items():
            if trg_id == trg_ref or trg_data.get("name") == trg_ref:
                return trg_data
        return None

    def resolve_page_id(self, flow_id, page_ref):
        if not page_ref: 
            return None
        # Check direct match
        if page_ref in self.pages.get(flow_id, {}):
            return page_ref
        
        # Check if page_ref is a full path and ends with one of our page IDs
        for page_id, page_data in self.pages.get(flow_id, {}).items():
            if page_ref.endswith(f"/{os.path.basename(page_id)}") or \
               page_ref == page_data.get("name") or \
               page_ref == page_data.get("displayName"):
                return page_id
        return None

    def check_unreachable_pages(self) -> List[Dict]:
        issues = []
        for flow_id, flow_data in self.flows.items():
            reachable = self.find_reachable_pages(flow_id)
            all_pages = set(self.pages.get(flow_id, {}).keys())
            unreachable = all_pages - reachable
            
            for page_id in unreachable:
                page_name = self.get_page_display_name(flow_id, page_id)
                issues.append({
                    "Flow": flow_data.get("displayName", flow_id),
                    "Page": page_name,
                    "Issue": "Unreachable Page",
                    "Severity": "Warning"
                })
        return issues

    def check_missing_event_handlers(self) -> List[Dict]:
        issues = []
        for flow_id, flow_data in self.flows.items():
            for page_id, page_data in self.pages.get(flow_id, {}).items():
                # Heuristic: If page has form (parameters), it should probably have event handlers
                # Or if it expects input (intents).
                
                # Check if it's an input page (has intents or form)
                has_intents = any(r.get("intent") for r in page_data.get("transitionRoutes", []))
                has_form = bool(page_data.get("form", {}).get("parameters"))
                
                if has_intents or has_form:
                    events = [h.get("event") for h in page_data.get("eventHandlers", [])]
                    # Also check reprompt event handlers in form parameters
                    if has_form:
                        for param in page_data["form"]["parameters"]:
                            for h in param.get("fillBehavior", {}).get("repromptEventHandlers", []):
                                events.append(h.get("event"))

                    has_no_input = any("no-input" in e for e in events if e)
                    has_no_match = any("no-match" in e for e in events if e)
                    
                    if not has_no_input or not has_no_match:
                        missing = []
                        if not has_no_input: missing.append("no-input")
                        if not has_no_match: missing.append("no-match")
                        
                        issues.append({
                            "Flow": flow_data.get("displayName", flow_id),
                            "Page": page_data.get("displayName", page_id),
                            "Issue": f"Missing Event Handlers: {', '.join(missing)}",
                            "Severity": "Warning"
                        })
        return issues

    def check_stuck_pages(self) -> List[Dict]:
        # Pages with no user input (no intents, no form) and no unconditional transition (true route)
        issues = []
        for flow_id, flow_data in self.flows.items():
            for page_id, page_data in self.pages.get(flow_id, {}).items():
                has_intents = any(r.get("intent") for r in page_data.get("transitionRoutes", []))
                has_form = bool(page_data.get("form", {}).get("parameters"))
                
                if not has_intents and not has_form:
                    # Check for unconditional route (condition="true" or empty condition with no intent)
                    # Actually DFCX "true" condition is explicitly "true" or sometimes just empty if it's the only thing? 
                    # Usually it's condition: "true"
                    has_true_route = False
                    for route in page_data.get("transitionRoutes", []):
                        condition = route.get("condition", "").lower()
                        if condition == "true":
                            has_true_route = True
                            break
                    
                    if not has_true_route:
                         issues.append({
                            "Flow": flow_data.get("displayName", flow_id),
                            "Page": page_data.get("displayName", page_id),
                            "Issue": "Potential Stuck Page (No Input, No True Route)",
                            "Severity": "Error"
                        })
        return issues

    def check_unused_route_groups(self) -> List[Dict]:
        issues = []
        for flow_id, flow_data in self.flows.items():
            used_trgs = set()
            
            # Check Flow usage
            for trg_ref in flow_data.get("transitionRouteGroups", []):
                trg = self.resolve_trg(flow_id, trg_ref)
                if trg:
                    used_trgs.add(trg.get("name"))

            # Check Pages usage
            for page_id, page_data in self.pages.get(flow_id, {}).items():
                for trg_ref in page_data.get("transitionRouteGroups", []):
                    trg = self.resolve_trg(flow_id, trg_ref)
                    if trg:
                        used_trgs.add(trg.get("name"))
            
            # Find unused
            for trg_id, trg_data in self.trgs.get(flow_id, {}).items():
                if trg_data.get("name") not in used_trgs and trg_id not in used_trgs:
                    issues.append({
                        "Flow": flow_data.get("displayName", flow_id),
                        "Page": "N/A",
                        "Issue": f"Unused Route Group: {trg_data.get('displayName')}",
                        "Severity": "Info"
                    })
        return issues

    def is_input_page(self, flow_id: str, page_id: str) -> bool:
        """Checks if a page waits for user input (has intents or form parameters)."""
        if page_id == "Start":
            # Start page of a flow *can* be an input page if it has intents in transition routes
            # But usually we treat it as a starting point. 
            # The notebook says: "Start page isn't treated as a page... input_page_ids.append(None)"
            # But then it checks intents.
            flow_data = self.flows.get(flow_id)
            if not flow_data: return False
            # Check transition routes for intents
            for route in flow_data.get("transitionRoutes", []):
                if route.get("intent"): return True
            # Check TRGs
            for trg_ref in flow_data.get("transitionRouteGroups", []):
                trg = self.resolve_trg(flow_id, trg_ref)
                if trg:
                    for route in trg.get("transitionRoutes", []):
                        if route.get("intent"): return True
            return False

        page_data = self.pages.get(flow_id, {}).get(page_id)
        if not page_data: return False
        
        # Check form parameters
        if page_data.get("form", {}).get("parameters"):
            return True
            
        # Check transition routes for intents
        for route in page_data.get("transitionRoutes", []):
            if route.get("intent"): return True
            
        # Check TRGs
        for trg_ref in page_data.get("transitionRouteGroups", []):
            trg = self.resolve_trg(flow_id, trg_ref)
            if trg:
                for route in trg.get("transitionRoutes", []):
                    if route.get("intent"): return True
                    
        return False

    def has_entry_fulfillment(self, flow_id: str, page_id: str) -> bool:
        if page_id == "Start":
            return False # Start page usually doesn't have entry fulfillment in the same way, or we ignore it for loops
        
        page_data = self.pages.get(flow_id, {}).get(page_id)
        if not page_data: return False
        
        ef = page_data.get("entryFulfillment", {})
        return bool(ef.get("messages") or ef.get("webhook"))

    def detect_possible_loops(self, threshold: int = 25) -> List[Dict]:
        issues = []
        
        for flow_id, flow_data in self.flows.items():
            # Get all input pages
            input_pages = [] # (page_id, page_name)
            
            # Add Start page if it acts as input or just as a root
            input_pages.append(("Start", "Start"))
            
            for page_id, page_data in self.pages.get(flow_id, {}).items():
                if self.is_input_page(flow_id, page_id):
                    input_pages.append((page_id, page_data.get("displayName", page_id)))
            
            for start_page_id, start_page_name in input_pages:
                self.detect_loops_rec(
                    flow_id=flow_id,
                    current_page_id=start_page_id,
                    current_page_name=start_page_name,
                    transition_count=0,
                    path=[],
                    issues=issues,
                    threshold=threshold,
                    visited_in_path=set()
                )
                
        return issues

    def detect_loops_rec(self, flow_id, current_page_id, current_page_name, transition_count, path, issues, threshold, visited_in_path):
        # Add current to path
        new_path = path + [current_page_name]
        
        # Check routes
        routes = []
        
        # Get routes based on page type
        if current_page_id == "Start":
            flow_data = self.flows.get(flow_id)
            if flow_data:
                routes.extend(flow_data.get("transitionRoutes", []))
                for trg_ref in flow_data.get("transitionRouteGroups", []):
                    trg = self.resolve_trg(flow_id, trg_ref)
                    if trg: routes.extend(trg.get("transitionRoutes", []))
                routes.extend(flow_data.get("eventHandlers", []))
        else:
            page_data = self.pages.get(flow_id, {}).get(current_page_id)
            if page_data:
                routes.extend(page_data.get("transitionRoutes", []))
                for trg_ref in page_data.get("transitionRouteGroups", []):
                    trg = self.resolve_trg(flow_id, trg_ref)
                    if trg: routes.extend(trg.get("transitionRoutes", []))
                routes.extend(page_data.get("eventHandlers", []))
                # Form reprompt handlers
                if page_data.get("form"):
                    for param in page_data["form"].get("parameters", []):
                        for h in param.get("fillBehavior", {}).get("repromptEventHandlers", []):
                            routes.append(h)

        for route in routes:
            target_page_ref = route.get("targetPage")
            target_flow_ref = route.get("targetFlow")
            
            if target_flow_ref:
                # Transition to another flow - end of loop check for this flow
                continue
                
            if target_page_ref:
                target_page_id = self.resolve_page_id(flow_id, target_page_ref)
                if not target_page_id: continue
                
                target_page_name = self.get_page_display_name(flow_id, target_page_id)
                
                # Determine cost
                cost = 2 if self.has_entry_fulfillment(flow_id, target_page_id) else 1
                new_count = transition_count + cost
                
                # Check if target is input page or threshold reached
                is_input = self.is_input_page(flow_id, target_page_id)
                # has_intent = bool(route.get("intent")) # Removed to allow detecting loops after intent transitions
                
                if is_input or new_count >= threshold:
                    # Base case
                    if new_count >= threshold:
                        # Found a long path/loop
                        issue_msg = f"Possible Infinite Loop (Depth {new_count}): {' -> '.join(new_path + [target_page_name])}"
                        # Check if we already have this issue to avoid duplicates
                        if not any(i['Issue'] == issue_msg for i in issues):
                            issues.append({
                                "Flow": self.flows[flow_id].get("displayName", flow_id),
                                "Page": current_page_name,
                                "Issue": issue_msg,
                                "Severity": "Warning"
                            })
                else:
                    # Recurse
                    if target_page_name in new_path:
                         # It is a loop
                         issue_msg = f"Infinite Loop Detected: {' -> '.join(new_path + [target_page_name])}"
                         if not any(i['Issue'] == issue_msg for i in issues):
                            issues.append({
                                "Flow": self.flows[flow_id].get("displayName", flow_id),
                                "Page": current_page_name,
                                "Issue": issue_msg,
                                "Severity": "Warning"
                            })
                    else:
                        self.detect_loops_rec(
                            flow_id, target_page_id, target_page_name, new_count, new_path, issues, threshold, visited_in_path
                        )

def render_graph_linter(credentials, agent_details):
    st.markdown("Analyze the agent's graph structure to find unreachable pages, stuck pages, missing event handlers, and unused route groups.")
    
    if st.button("Run Graph Analysis"):
        try:
            agent_name = agent_details['name']
            temp_dir = linter.export_and_extract_agent(credentials, agent_details)
            st.success("Agent exported successfully.")
            
            with st.spinner("Analyzing Agent Graph..."):
                graph = OfflineFlowGraph(temp_dir)
                
                all_issues = []
                all_issues.extend(graph.check_unreachable_pages())
                all_issues.extend(graph.check_missing_event_handlers())
                all_issues.extend(graph.check_stuck_pages())
                all_issues.extend(graph.check_unused_route_groups())
                all_issues.extend(graph.detect_possible_loops())
                
                st.session_state['graph_issues'] = all_issues
                
            shutil.rmtree(temp_dir)
            
        except Exception as e:
            st.error(f"Error: {e}")
            st.exception(e)

    if 'graph_issues' in st.session_state:
        all_issues = st.session_state['graph_issues']
        if all_issues:
            st.warning(f"Found {len(all_issues)} issues.")
            df = pd.DataFrame(all_issues)
            
            from modules import ui_utils
            ui_utils.render_dataframe_with_filter(df, filter_col="Flow")
        else:
            st.success("No graph issues found!")
