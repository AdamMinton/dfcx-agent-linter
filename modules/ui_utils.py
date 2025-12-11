import streamlit as st
import pandas as pd

def render_dataframe_with_filter(df: pd.DataFrame, filter_col: str = "Flow", title: str = None):
    """
    Renders a DataFrame with an optional multiselect filter.
    
    Args:
        df: The DataFrame to display.
        filter_col: The column to filter by (default: "Flow").
        title: Optional title to display before the DataFrame.
    """
    if title:
        st.markdown(f"### {title}")

    if df.empty:
        st.caption("No issues found to display.")
        return

    if filter_col and filter_col in df.columns:
        all_values = sorted(df[filter_col].unique())
        selected_values = st.multiselect(f"Filter by {filter_col}", options=all_values, default=all_values)
        
        if selected_values:
            filtered_df = df[df[filter_col].isin(selected_values)]
            st.dataframe(filtered_df, width='stretch')
        else:
            st.caption(f"Select {filter_col}s to view data.")
    else:
        st.dataframe(df, width='stretch')
