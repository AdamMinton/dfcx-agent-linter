# Learnings & Context for Future Conversations

## `cxlint` Library Issues
The `cxlint` library (v1.0.0+) has several known bugs that require monkeypatching to work reliably in a production or web environment:

1.  **`MarkupError` in Logging**:
    -   **Issue**: `cxlint` uses the `rich` library for logging but fails to escape resource display names. If a display name contains `[` or `]`, `rich` interprets it as a tag, causing a crash.
    -   **Fix**: Monkeypatch `cxlint.rules.logger.RulesLogger.generic_logger` to escape display names using `rich.markup.escape` before logging.

2.  **`UnboundLocalError` in Rules**:
    -   **Issue**: Several rules (`entity_type_naming_convention`, `test_case_naming_convention`, `webhook_naming_conventions`) attempt to access a local variable `res` that is only initialized if a `naming_pattern` exists. If no pattern is provided, the code crashes.
    -   **Fix**: Monkeypatch these rule methods to initialize `res = True` by default.

## Streamlit & Monkeypatching
When monkeypatching classes in a Streamlit application, special care must be taken due to its hot-reloading mechanism:

1.  **Recursion Risk**:
    -   **Issue**: If you patch a method like `Class.method = new_method` where `new_method` calls the original `Class.method`, Streamlit's reload will cause `new_method` to call *itself* (the previous patch) recursively, leading to a stack overflow.
    -   **Fix**: Always implement a "restore-then-patch" pattern:
        ```python
        if hasattr(Class, '_original_method'):
            Class.method = Class._original_method  # Restore first
        Class._original_method = Class.method      # Save original
        Class.method = new_method                  # Apply patch
        ```

## Project Context
-   **Repo**: `dfcx-agent-linter`
-   **Tech Stack**: Streamlit, Google Cloud Run, DFCX API, `cxlint`.
-   **Key Modules**:
    -   `modules/linter.py`: Contains the `cxlint` runner and all the critical monkeypatches.

## Recent Learnings (Flow Filtering & Test Runner)

1.  **`dfcx_scrapi` vs Raw Client**:
    -   `dfcx_scrapi.core.test_cases.TestCases.list_test_cases` returns shallow objects (no conversation turns) by default and does not support the `view` parameter.
    -   To filter test cases by visited pages/flows, we must use the raw `google.cloud.dialogflowcx_v3.TestCasesClient` with `view=TestCaseView.FULL` to fetch conversation turns.

2.  **Streamlit State Persistence**:
    -   When generating reports via a button click (e.g., "Run CXLint"), results must be stored in `st.session_state`.
    -   If not persisted, interacting with any subsequent widget (like a filter multiselect) triggers a rerun, resetting the script and clearing the results because the button is no longer "clicked".

3.  **Page ID Mapping**:
    -   `dfcx_scrapi.core.pages.Pages.get_pages_map` (and `list_pages`) often excludes the special "Start Page" of a flow.
    -   When building a `Page ID -> Flow Name` map, explicitly add the Start Page (e.g., `.../flows/{flow_id}/pages/Start`) to ensure complete coverage, otherwise test cases landing on the Start Page won't be correctly mapped to the flow.
