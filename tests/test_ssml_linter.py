import unittest
import sys
import os
import xml.etree.ElementTree as ET

# Add the repo root to path so we can import modules
sys.path.append("/usr/local/google/home/adamminton/Documents/git_repos/dfcx-agent-linter")

from modules.ssml_linter import validate_ssml, find_ssml_in_fulfillment

class TestSSMLValidation(unittest.TestCase):
    def test_validate_ssml_valid(self):
        text = "<speak>Hello world</speak>"
        is_valid, err = validate_ssml(text)
        self.assertTrue(is_valid)
        self.assertIsNone(err)

    def test_validate_ssml_invalid_tag(self):
        text = "<speak>Hello <break time='3s'> world</speak>" # Missing closing / for break if strict XML? 
        # Actually <break time='3s'> is not valid XML if not closed, should be <break time='3s'/>
        # Let's see if ElementTree catches it.
        is_valid, err = validate_ssml(text)
        self.assertFalse(is_valid)
        self.assertIn("mismatched tag", err.lower())

    def test_validate_ssml_valid_complex(self):
        text = """<speak>
            <p>
                <s>This is a sentence.</s>
            </p>
        </speak>"""
        is_valid, err = validate_ssml(text)
        self.assertTrue(is_valid)

    def test_validate_ssml_plain_text(self):
        text = "Just plain text"
        is_valid, err = validate_ssml(text)
        self.assertTrue(is_valid) # Should be ignored

    def test_find_ssml_in_fulfillment(self):
        fulfillment = {
            "messages": [
                {
                    "text": {
                        "text": ["<speak>Hi</speak>", "Hello"]
                    }
                },
                {
                    "outputAudioText": {
                        "ssml": "<speak>Audio</speak>"
                    }
                }
            ]
        }
        
        results = list(find_ssml_in_fulfillment(fulfillment, "root"))
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0][1], "<speak>Hi</speak>")
        self.assertEqual(results[1][1], "<speak>Audio</speak>")

if __name__ == '__main__':
    unittest.main()
