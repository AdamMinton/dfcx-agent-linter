import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta
import pandas as pd
# Import the class to test. Assuming cx_test_case_runner is in the python path or same directory.
# We might need to adjust sys.path if running from a different directory.
import sys
import os
from unittest.mock import MagicMock

# Mock dfcx_scrapi before importing cx_test_case_runner
sys.modules['dfcx_scrapi'] = MagicMock()
sys.modules['dfcx_scrapi.core'] = MagicMock()
sys.modules['dfcx_scrapi.core.intents'] = MagicMock()
sys.modules['dfcx_scrapi.core.flows'] = MagicMock()
sys.modules['dfcx_scrapi.core.pages'] = MagicMock()
sys.modules['dfcx_scrapi.core.agents'] = MagicMock()
sys.modules['dfcx_scrapi.core.test_cases'] = MagicMock()

# sys.modules['google'] = MagicMock() # Do not mock root google package
sys.modules['google.cloud'] = MagicMock()
sys.modules['google.cloud.storage'] = MagicMock()
sys.modules['google.cloud.bigquery'] = MagicMock()
sys.modules['google.auth'] = MagicMock()
sys.modules['google.auth.transport'] = MagicMock()
sys.modules['google.auth.transport.requests'] = MagicMock()
sys.modules['google.api_core'] = MagicMock()
sys.modules['google.api_core.exceptions'] = MagicMock()
sys.modules['pandas_gbq'] = MagicMock()
sys.modules['ratelimit'] = MagicMock()

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from modules.test_runner import CxTestCasesHelper

class TestCxTestCasesHelperEnhancements(unittest.TestCase):
    def setUp(self):
        self.agent_id = "projects/p/locations/l/agents/a"
        self.bq_project = "bq-p"
        self.bq_table = "bq-t"
        
        # Patch dependencies
        self.patcher_agents = patch('modules.test_runner.Agents')
        self.patcher_intents = patch('modules.test_runner.Intents')
        self.patcher_flows = patch('modules.test_runner.Flows')
        self.patcher_pages = patch('modules.test_runner.Pages')
        self.patcher_testcases = patch('modules.test_runner.TestCases')
        
        self.mock_agents = self.patcher_agents.start()
        self.mock_intents = self.patcher_intents.start()
        self.mock_flows = self.patcher_flows.start()
        self.mock_pages = self.patcher_pages.start()
        self.mock_testcases = self.patcher_testcases.start()
        
        self.helper = CxTestCasesHelper(self.agent_id)
        
        # Mock internal methods to avoid API calls
        self.helper.get_agent = MagicMock()
        self.helper.get_agent.return_value.display_name = "Test Agent"
        
        self.helper.dfcx_f.get_flows_map = MagicMock(return_value={
            "flow-1": "Flow A",
            "flow-2": "Flow B"
        })
        
        # Mock convert_flow to use the map we just defined
        # Note: convert_flow is an instance method, so we can mock it on the instance if we want,
        # or just let it run if it's simple. It uses self.convert_flow(..., flows_map)
        # The original implementation:
        # def convert_flow(self, flow_id, flows_map):
        #     if flow_id.split('/')[-1] == '-': return ''
        #     if flow_id in flows_map.keys(): return flows_map[flow_id]
        #     return 'Default Start Flow'
        # We can let it run or mock it. Let's let it run but ensure flows_map is passed correctly.
        # Actually, get_test_case_results calls self.dfcx_f.get_flows_map again.
        # We mocked self.dfcx_f.get_flows_map above.
        
    def tearDown(self):
        self.patcher_agents.stop()
        self.patcher_intents.stop()
        self.patcher_flows.stop()
        self.patcher_pages.stop()
        self.patcher_testcases.stop()

    def create_mock_test_case(self, name, display_name, flow_id, result, test_time=None):
        mock_tc = MagicMock()
        mock_tc.name = name
        mock_tc.display_name = display_name
        mock_tc.test_config.flow = flow_id
        mock_tc.last_test_result.test_result = result
        mock_tc.last_test_result.test_time = test_time
        mock_tc.tags = []
        mock_tc.creation_time = datetime.now()
        return mock_tc

    def test_flow_filtering(self):
        # Setup test cases
        tc1 = self.create_mock_test_case("tc1", "Test 1", "flow-1", "TestResult.PASSED")
        tc2 = self.create_mock_test_case("tc2", "Test 2", "flow-2", "TestResult.PASSED")
        
        # Mock list_test_cases
        mock_tc_instance = self.mock_testcases.return_value
        mock_tc_instance.list_test_cases.return_value = [tc1, tc2]
        
        # Run with filter
        df = self.helper.get_test_case_results(flow_filter=["Flow A"])
        
        # Verify
        self.assertEqual(len(df), 1)
        self.assertEqual(df.iloc[0]['test_case_display_name'], "Test 1")

    def test_recency_check(self):
        # Setup test cases
        now = datetime.now()
        old_time = now - timedelta(days=10)
        recent_time = now - timedelta(days=1)
        
        tc1 = self.create_mock_test_case("tc1", "Old Test", "flow-1", "TestResult.PASSED", test_time=old_time)
        tc2 = self.create_mock_test_case("tc2", "Recent Test", "flow-1", "TestResult.PASSED", test_time=recent_time)
        
        mock_tc_instance = self.mock_testcases.return_value
        mock_tc_instance.list_test_cases.return_value = [tc1, tc2]
        mock_tc_instance.batch_run_test_cases.return_value.results = []
        
        # Run with recency_days=5
        self.helper.get_test_case_results(recency_days=5)
        
        # Verify batch_run_test_cases called with tc1
        mock_tc_instance.batch_run_test_cases.assert_called()
        call_args = mock_tc_instance.batch_run_test_cases.call_args[0][0]
        self.assertIn("tc1", call_args)
        self.assertNotIn("tc2", call_args)

    def test_batching(self):
        # Setup many test cases that need retesting
        tcs = []
        for i in range(50):
            tcs.append(self.create_mock_test_case(f"tc{i}", f"Test {i}", "flow-1", "TestResult.TEST_RESULT_UNSPECIFIED"))
        
        mock_tc_instance = self.mock_testcases.return_value
        mock_tc_instance.list_test_cases.return_value = tcs
        mock_tc_instance.batch_run_test_cases.return_value.results = []
        
        # Run with limit=20
        self.helper.get_test_case_results(limit=20)
        
        # Verify batch_run_test_cases called 3 times (20, 20, 10)
        self.assertEqual(mock_tc_instance.batch_run_test_cases.call_count, 3)
        
        # Check chunk sizes
        calls = mock_tc_instance.batch_run_test_cases.call_args_list
        self.assertEqual(len(calls[0][0][0]), 20)
        self.assertEqual(len(calls[1][0][0]), 20)
        self.assertEqual(len(calls[2][0][0]), 10)

if __name__ == '__main__':
    unittest.main()
