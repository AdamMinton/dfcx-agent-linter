import streamlit as st
import pandas as pd
import random
import threading
import logging
import requests
import time
import uuid
from datetime import datetime, timedelta

from dfcx_scrapi.core.intents import Intents
from dfcx_scrapi.core.flows import Flows
from dfcx_scrapi.core.pages import Pages
from dfcx_scrapi.core.agents import Agents
from dfcx_scrapi.core.test_cases import TestCases
from google.cloud import dialogflowcx_v3
from google.cloud import storage
from google.auth.transport.requests import Request
from ratelimit import limits, sleep_and_retry
from google.api_core.exceptions import ResourceExhausted

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# 60 calls per minute
CALLS = 60
RATE_LIMIT = 60
MAX_RETRIES = 5
RETRY_DELAY = 30

@sleep_and_retry
@limits(calls=CALLS, period=RATE_LIMIT)
def check_limit():
    ''' Empty function just to check for calls to API '''
    return

class CxTestCasesHelper:

    def __init__(self, agent_id, creds=None):
        self.agent_project_id = agent_id.split("/")[1]
        self.agent_location_id = agent_id.split("/")[3]
        self.agent_id_full = agent_id
        self.agent_id = agent_id.split("/")[5]
        # dfcx_scrapi handles regional endpoints via agent_id for some classes,
        # but TestCases and Pages need manual client_options configuration.
        self.dfcx_a = Agents(creds=creds, agent_id=agent_id)
        self.dfcx_i = Intents(creds=creds, agent_id=agent_id)
        self.dfcx_f = Flows(creds=creds, agent_id=agent_id)
        self.dfcx_p = Pages(creds=creds)
        self.dfcx_tc = TestCases(creds=creds, agent_id=agent_id)
        
        # Manually set client_options for regional agents
        if self.agent_location_id != "global":
            client_options = self.dfcx_tc._set_region(agent_id)
            self.dfcx_tc.client_options = client_options
            self.dfcx_p.client_options = client_options
            self.dfcx_f.client_options = client_options
            self.dfcx_i.client_options = client_options
            self.dfcx_a.client_options = client_options
        else:
            # Explicitly set to None for global to avoid AttributeError later
            self.dfcx_tc.client_options = None
            self.dfcx_p.client_options = None
            self.dfcx_f.client_options = None
            self.dfcx_i.client_options = None
            self.dfcx_a.client_options = None

    def convert_flow(self, flow_id, flows_map):
        if flow_id.split('/')[-1] == '-':
            return ''
        if flow_id in flows_map.keys():
            return flows_map[flow_id]
        return 'Default Start Flow'

    def handle_dfcx_quota(func):
        def wrapped_func(*args, **kwargs):
            for i in range(MAX_RETRIES):
                try:
                    check_limit()
                    return func(*args, **kwargs)
                except ResourceExhausted:
                    exponential_delay = RETRY_DELAY * (2**i + random.random())
                    print(f'API returned rate limit error. Waiting {exponential_delay} seconds and trying again...')
                    time.sleep(exponential_delay)
            raise Exception("ERROR: Request failed too many times.")
        return wrapped_func
        
    @handle_dfcx_quota
    def get_agent(self, agent_id):
        return self.dfcx_a.get_agent(agent_id=agent_id)
        
    @handle_dfcx_quota
    def get_intents_map(self, dfcx_i, agent_id):
        return self.dfcx_i.get_intents_map(agent_id)

    @handle_dfcx_quota
    def get_flows_map(self, dfcx_f, agent_id):
        return self.dfcx_f.get_flows_map(agent_id)

    @handle_dfcx_quota
    def get_pages_map(self, dfcx_p, flow_id):
        return self.dfcx_p.get_pages_map(flow_id)

    @handle_dfcx_quota
    def list_flows(self, dfcx_f, agent_id):
        return self.dfcx_f.list_flows(agent_id)

    @handle_dfcx_quota
    def get_page(self, dfcx_p, page_id):
        return self.dfcx_p.get_page(page_id=page_id)

    @handle_dfcx_quota
    def get_test_case_results(self, retest_all=False, flow_filter=None, tag_filter=None, limit=None, recency_days=None, progress_callback=None):
        '''
        Fetches test cases and filters them.
        If flow_filter is provided, it checks if the test case touches any of the selected flows.
        '''

        agent = self.get_agent(agent_id=self.agent_id_full)
        flows_map = self.dfcx_f.get_flows_map(self.agent_id_full)
        
        # Pre-fetch all pages to map Page ID -> Flow Name for deep filtering
        page_to_flow_map = {}
        if flow_filter:
            # We only need this if we are filtering by flow
            # This might be expensive if there are many flows/pages
            # But it's necessary to know which flow a page belongs to
            for flow_id, flow_name in flows_map.items():
                # We need page IDs. 
                # dfcx_scrapi get_pages_map returns {page_id: page_name}
                # We need the reverse or just to know flow_name for a page_id
                
                # 1. Add Start Page explicitly (list_pages doesn't return it)
                start_page_id = f"{flow_id}/pages/Start"
                page_to_flow_map[start_page_id] = flow_name
                
                try:
                    p_map = self.dfcx_p.get_pages_map(flow_id)
                    for pid in p_map.keys():
                        page_to_flow_map[pid] = flow_name
                except Exception as e:
                    logging.warning(f"Failed to get pages for flow {flow_name} ({flow_id}): {e}")
            
            logging.info(f"Built page_to_flow_map with {len(page_to_flow_map)} entries.")

        # Use raw client to get FULL view (needed for conversation turns)
        client = dialogflowcx_v3.TestCasesClient(
            credentials=self.dfcx_tc.creds,
            client_options=self.dfcx_tc.client_options
        )
        request = dialogflowcx_v3.ListTestCasesRequest(
            parent=self.agent_id_full,
            view=dialogflowcx_v3.ListTestCasesRequest.TestCaseView.FULL,
            page_size=20
        )
        test_cases = client.list_test_cases(request=request)
        retest = []
        retest_names = []
        results = {}
        results_by_id = {}

        display_names = []
        ids = []
        short_ids = []
        tags = []
        creation_times = []
        flows = []
        test_results = []
        test_times = []
        passed = []
        not_runnable = []
        deep_links = []

        # Filter test cases first if flow_filter is provided
        filtered_test_cases = []
        
        # Convert test_cases generator to list if needed, or iterate
        # list_test_cases returns a List usually
        
        for response in test_cases:
            # Flow Filter Logic
            if flow_filter:
                include_tc = False
                
                # 1. Check Start Flow
                start_flow_name = self.convert_flow(response.test_config.flow, flows_map)
                if start_flow_name in flow_filter:
                    include_tc = True
                
                # 2. Check Touched Flows (Deep Filter)
                if not include_tc:
                    # Check conversation turns
                    for turn in response.test_case_conversation_turns:
                        # Check virtual agent output for current page
                        if turn.virtual_agent_output and turn.virtual_agent_output.current_page:
                            page_id = turn.virtual_agent_output.current_page.name
                            # page_id is full resource name usually
                            # But get_pages_map usually returns full resource name as key?
                            # Let's check if we can match it
                            
                            # If page_id is in our map, we know the flow
                            if page_id in page_to_flow_map:
                                flow_name = page_to_flow_map[page_id]
                                if flow_name in flow_filter:
                                    include_tc = True
                                    break
                            
                            # Also check if it's a Flow ID directly (Start Page)
                            # Sometimes current_page might be the flow start? 
                            # Actually current_page.name is usually the page resource name.
                            # If it's the start page, it might be just the flow ID or end with /pages/Start
                            
                            # If we can't find it in map, maybe it's a flow start page?
                            # Flow start page doesn't always show up in get_pages_map
                            # But usually we can infer flow from the page ID structure?
                            # projects/.../flows/{flow_id}/pages/{page_id}
                            # We can extract flow_id from the string
                            if "flows/" in page_id:
                                try:
                                    # Extract flow id
                                    # .../flows/FLOW_ID/pages/...
                                    parts = page_id.split('/')
                                    if 'flows' in parts:
                                        f_idx = parts.index('flows')
                                        if f_idx + 1 < len(parts):
                                            fid = parts[f_idx+1]
                                            # Reconstruct full flow ID or just match by suffix?
                                            # flows_map keys are usually full IDs
                                            # Let's try to find the flow in flows_map
                                            found_flow = False
                                            for f_full_id, f_name in flows_map.items():
                                                if f_full_id.endswith(f"/flows/{fid}"):
                                                    if f_name in flow_filter:
                                                        include_tc = True
                                                        found_flow = True
                                                    break
                                            if found_flow:
                                                break
                                except:
                                    pass

                if not include_tc:
                    continue
            
            # Filter by tags
            if tag_filter:
                tc_tags = list(response.tags)
                if not set(tag_filter).intersection(set(tc_tags)):
                    continue

            filtered_test_cases.append(response)
        
        test_cases = filtered_test_cases

        for response in test_cases:
            #print(response)
            results[response.display_name] = str(response.last_test_result.test_result)
            
            # Determine if we should retest
            should_retest = False
            if retest_all:
                should_retest = True
            elif str(response.last_test_result.test_result) == 'TestResult.TEST_RESULT_UNSPECIFIED':
                should_retest = True
            elif recency_days is not None:
                # Check if test is too old
                if response.last_test_result.test_time:
                    last_run = response.last_test_result.test_time
                    if last_run:
                        # If last_run is older than recency_days
                        cutoff = datetime.now(last_run.tzinfo) - timedelta(days=recency_days)
                        if last_run < cutoff:
                            should_retest = True
                else:
                    # Never run
                    should_retest = True

            if should_retest:
                retest.append(response.name)
                retest_names.append(response.display_name)
                
            # Collect additional information for dataframe
            display_names.append(response.display_name)
            ids.append(response.name)
            short_ids.append(response.name.split('/')[-1])
            tags.append(list(response.tags)) # Convert RepeatedScalarContainer to list
            creation_times.append(response.creation_time)
            flows.append(self.convert_flow(response.test_config.flow, flows_map))
            test_results.append(str(response.last_test_result.test_result))
            test_times.append(response.last_test_result.test_time)
            # Check for PASSED in string representation or if it is the enum value 1
            raw_result = response.last_test_result.test_result
            is_passed = 'PASSED' in str(raw_result) or raw_result == 1
            passed.append(is_passed)
            not_runnable.append('UNSPECIFIED' in str(raw_result) or raw_result == 0)
            
            # Generate Deep Link
            link = f"https://conversational-agents.cloud.google.com/projects/{self.agent_project_id}/locations/{self.agent_location_id}/agents/{self.agent_id}/(testCaseV2s/{response.name.split('/')[-1]}/resultV2s//right-panel:simulator)"
            deep_links.append(link)

        # Create dataframe
        test_case_df = pd.DataFrame({
            'agent_project_id': self.agent_project_id,
            'agent_location_id': self.agent_location_id,
            'agent_id': self.agent_id,
            'agent_display_name': agent.display_name,
            'test_case_display_name': display_names, 
            'id': ids, 
            'short_id': short_ids, 
            'tags': tags, 
            'creation_time': creation_times, 
            'start_flow': flows, 
            'test_result': test_results, 
            'passed': passed, 
            'not_runnable': not_runnable, 
            'test_time': test_times,
            'deep_link': deep_links
        })


        # Retest any that haven't been run yet
        logging.info(f'To retest:{len(retest)}')
        
        if len(retest) > 0:
            # Batching logic
            batch_size = limit if limit else 20 # Default to 20 if not specified, or user specified limit
            
            chunks = [retest[i:i + batch_size] for i in range(0, len(retest), batch_size)]
            total_chunks = len(chunks)
            
            for i, chunk in enumerate(chunks):
                if progress_callback:
                    # Calculate progress from 0.2 to 1.0 based on chunks
                    progress = 0.2 + (0.8 * (i / total_chunks))
                    progress_callback(progress, f"Running batch {i+1}/{total_chunks} ({len(chunk)} tests)...")
                    
                logging.info(f'Running batch of {len(chunk)} tests...')
                try:
                    response = self.dfcx_tc.batch_run_test_cases(chunk, self.agent_id_full)
                    for result in response.results:
                        # Results may not be in the same order as they went in (oh well)
                        testCaseId_full = '/'.join(result.name.split('/')[:-2])
                        
                        # Update dataframe where id = testcaseId_full
                        test_case_df.loc[test_case_df['id'] == testCaseId_full, 'short_id'] = testCaseId_full.split('/')[-1]
                        test_case_df.loc[test_case_df['id'] == testCaseId_full, 'test_result'] = str(result.test_result)
                        test_case_df.loc[test_case_df['id'] == testCaseId_full, 'test_time'] = result.test_time
                        
                        # Check for PASSED (handle int or string)
                        raw_res = result.test_result
                        is_passed = 'PASSED' in str(raw_res) or raw_res == 1
                        test_case_df.loc[test_case_df['id'] == testCaseId_full, 'passed'] = is_passed
                        test_case_df.loc[test_case_df['id'] == testCaseId_full, 'not_runnable'] = 'UNSPECIFIED' in str(raw_res) or raw_res == 0
                except Exception as e:
                    logging.error(f"Error running batch: {e}")

        return test_case_df

        
    def execute(self, flow_filter=None, tag_filter=None, limit=None, recency_days=None, progress_callback=None):
        test_guid = uuid.uuid4()
        test_start_time = datetime.now()

        logging.info(f"AgentId: {self.agent_id}, Test GUID:{test_guid}, Start time: {test_start_time}")

        intents_map =self.get_intents_map(self.dfcx_i, self.agent_id_full)
        flows_map = self.get_flows_map(self.dfcx_f, self.agent_id_full)
        pages_map = {}

        for flow_id in flows_map.keys():
            pages_map[flow_id] = self.get_pages_map(self.dfcx_p, flow_id)
        
        flow_data_list = self.list_flows(self.dfcx_f,self.agent_id_full)

        logging.info('Pre-processing complete')
        
        if progress_callback:
            progress_callback(0.1, "Fetching test cases...")

        test_case_results_df = self.get_test_case_results(retest_all=True, flow_filter=flow_filter, tag_filter=tag_filter, limit=limit, recency_days=recency_days, progress_callback=progress_callback)

        test_case_results_df["test_run_guid"] = str(test_guid)
        test_case_results_df["test_run_timestamp"] = test_start_time
        test_case_results_df["test_time"] = test_case_results_df["test_time"]
        test_case_results_df.rename(columns = {'id':'test_case_id'}, inplace = True) #rename 'id' to 'test_case_id'

        # only select the columns
        test_case_results_df = test_case_results_df[
            [
                'test_run_guid',
                'test_run_timestamp',
                'agent_id',
                'agent_display_name',
                'test_case_id',
                'test_case_display_name',
                'start_flow',
                'passed',
                'not_runnable',
                'test_time',
                'test_result', # Added for debugging
                'tags',
                'deep_link'
            ]
        ]

        return test_guid, test_case_results_df

def render_test_runner(creds, agent_details):
    st.markdown("Run and analyze test cases with advanced filtering options, including deep flow filtering and tag filtering.")
    
    if not creds:
        st.warning("Credentials not available.")
        return

    agent_id = agent_details['name']
    
    # Configuration
    col1, col2 = st.columns(2)
    with col1:
        limit = st.number_input("Batch Size (Concurrency Limit)", min_value=1, max_value=100, value=20)
    
    with col2:
        recency_days = st.number_input("Recency Check (Days)", min_value=0, value=0, help="0 to disable recency check")
    
    # Fetch Flows and Tags for Filter
    if st.button("Fetch Filters Data"):
        try:
            with st.spinner("Fetching flows and tags..."):
                # Flows
                flows_instance = Flows(creds=creds, agent_id=agent_id)
                
                # Tags (requires fetching test cases)
                tc_instance = TestCases(creds=creds, agent_id=agent_id)
                
                # Manually set client_options if regional
                location = agent_id.split("/")[3]
                if location != "global":
                    client_options = tc_instance._set_region(agent_id)
                    flows_instance.client_options = client_options
                    tc_instance.client_options = client_options
                
                flows_map = flows_instance.get_flows_map(agent_id=agent_id)
                st.session_state['flows_map'] = flows_map
                
                test_cases = tc_instance.list_test_cases(agent_id=agent_id)
                all_tags = set()
                for tc in test_cases:
                    # tc.tags is a RepeatedScalarContainer, convert to list
                    if tc.tags:
                        all_tags.update(list(tc.tags))
                st.session_state['available_tags'] = sorted(list(all_tags))
                
            st.success("Filters data fetched successfully!")
        except Exception as e:
            st.error(f"Error fetching filters data: {e}")
    
    flows_map = st.session_state.get('flows_map', {})
    flow_options = list(flows_map.values()) if flows_map else []
    
    available_tags = st.session_state.get('available_tags', [])
    
    col_filter1, col_filter2 = st.columns(2)
    with col_filter1:
        selected_flows = st.multiselect("Filter by Flow (Any Touched)", options=flow_options)
    with col_filter2:
        selected_tags = st.multiselect("Filter by Tags", options=available_tags)
    
    if st.button("Run Tests"):
        status_msg = st.empty()
        status_msg.info("Initializing Test Runner...")
        try:
            runner = CxTestCasesHelper(agent_id, creds=creds)
            
            # Pass 0 as None for recency if user didn't set it
            r_days = recency_days if recency_days > 0 else None
            
            # Create a progress bar
            progress_bar = st.progress(0, text="Starting tests...")
            
            # We need to modify execute to support progress callback or we can just fake it if we can't easily modify execute
            # But better to modify execute to accept a callback
            result, df = runner.execute(flow_filter=selected_flows, tag_filter=selected_tags, limit=limit, recency_days=r_days, progress_callback=lambda p, t: progress_bar.progress(p, text=t))
            
            progress_bar.empty() # Remove progress bar on completion
            status_msg.empty() # Remove status message
            st.session_state['test_runner_result'] = result
            st.session_state['test_runner_df'] = df
            st.success(f"Tests completed! Run GUID: {result}")
                
        except Exception as e:
            st.error(f"Error running tests: {e}")

    # Render results if they exist in session state
    if 'test_runner_df' in st.session_state:
        df = st.session_state['test_runner_df']
        
        # Metrics
        total = len(df)
        passed_count = df['passed'].sum()
        failed_count = total - passed_count
        pass_rate = (passed_count / total * 100) if total > 0 else 0
        
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Tests", total)
        m2.metric("Passed", int(passed_count))
        m3.metric("Failed", int(failed_count))
        m4.metric("Pass Rate", f"{pass_rate:.1f}%")
        
        # Filter for Failed
        show_failed = st.checkbox("Show Failed Only")
        if show_failed:
            df_display = df[~df['passed']]
        else:
            df_display = df
        
        st.dataframe(
            df_display,
            column_config={
                "deep_link": st.column_config.LinkColumn(
                    "Deep Link",
                    help="Link to Test Case in Dialogflow CX Console",
                    display_text="Open in Console"
                )
            }
        )
