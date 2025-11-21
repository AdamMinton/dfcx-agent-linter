import sys
import os

try:
    import streamlit
    print("Streamlit imported successfully")
    import google.cloud.dialogflowcx_v3
    print("DFCX Client imported successfully")
    from cxlint.cxlint import CxLint
    print("CxLint imported successfully")
except ImportError as e:
    print(f"Import failed: {e}")
    sys.exit(1)

print("All critical imports successful.")
