"""Beyond the Crowd Score — Streamlit app."""

import pandas as pd
import streamlit as st

from src.app_data import EXPECTED_ROWS, load_tables

st.set_page_config(page_title="Beyond the Crowd Score", page_icon="🎬", layout="wide")
st.title("Beyond the Crowd Score")

tables = load_tables()

st.subheader("Data check")
st.dataframe(pd.DataFrame({
    "rows":     {k: len(v) for k, v in tables.items()},
    "expected": EXPECTED_ROWS,
    "columns":  {k: v.shape[1] for k, v in tables.items()},
}))