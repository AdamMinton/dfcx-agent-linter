import unittest
import os
import json
import shutil
import tempfile
from modules.graph_linter import OfflineFlowGraph
from modules.search_linter import AgentSearcher

class TestNewModules(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.flows_dir = os.path.join(self.test_dir, "flows")
        os.makedirs(self.flows_dir)
        
        # Create a mock flow with a loop
        self.flow_name = "Default Start Flow"
        self.flow_dir = os.path.join(self.flows_dir, self.flow_name)
        os.makedirs(self.flow_dir)
        
        # Flow.json
        flow_data = {
            "name": "00000000-0000-0000-0000-000000000000",
            "displayName": self.flow_name,
            "transitionRoutes": [
                {"intent": "start_intent", "targetPage": "Page1"}
            ]
        }
        with open(os.path.join(self.flow_dir, f"{self.flow_name}.json"), "w") as f:
            json.dump(flow_data, f)
            
        # Pages
        self.pages_dir = os.path.join(self.flow_dir, "pages")
        os.makedirs(self.pages_dir)
        
        # Page1 -> Page2
        page1_data = {
            "name": "11111111-1111-1111-1111-111111111111",
            "displayName": "Page1",
            "transitionRoutes": [
                {"condition": "true", "targetPage": "Page2"}
            ]
        }
        with open(os.path.join(self.pages_dir, "Page1.json"), "w") as f:
            json.dump(page1_data, f)
            
        # Page2 -> Page1 (Loop)
        page2_data = {
            "name": "22222222-2222-2222-2222-222222222222",
            "displayName": "Page2",
            "transitionRoutes": [
                {"condition": "true", "targetPage": "Page1"}
            ]
        }
        with open(os.path.join(self.pages_dir, "Page2.json"), "w") as f:
            json.dump(page2_data, f)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_loop_detection(self):
        graph = OfflineFlowGraph(self.test_dir)
        issues = graph.detect_possible_loops(threshold=5)
        
        # Should find a loop
        found_loop = False
        for issue in issues:
            if "Possible Infinite Loop" in issue["Issue"] or "Infinite Loop Detected" in issue["Issue"]:
                found_loop = True
                print(f"Found Loop Issue: {issue['Issue']}")
                break
        
        self.assertTrue(found_loop, "Should detect the infinite loop between Page1 and Page2")

    def test_search(self):
        searcher = AgentSearcher(self.test_dir)
        
        # Search for "Page1"
        df = searcher.search("Page1", scope="All")
        self.assertFalse(df.empty, "Should find 'Page1' in transition routes")
        print(f"Found {len(df)} matches for 'Page1'")
        
        # Search for "start_intent"
        df_intent = searcher.search("start_intent", scope="All")
        self.assertFalse(df_intent.empty, "Should find 'start_intent'")
        print(f"Found {len(df_intent)} matches for 'start_intent'")

if __name__ == "__main__":
    unittest.main()
