import pandas as pd
import streamlit as st

from src.app_data import EXPECTED_ROWS, load_tables

st.header("Findings")

tables = load_tables()

st.subheader("Data check")
st.dataframe(pd.DataFrame({
    "rows":     {k: len(v) for k, v in tables.items()},
    "expected": EXPECTED_ROWS,
    "columns":  {k: v.shape[1] for k, v in tables.items()},
}))