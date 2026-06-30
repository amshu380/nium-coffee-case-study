import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import pandas as pd
import streamlit as st

load_dotenv()


@st.cache_resource
def get_engine():
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL not found in .env")
    return create_engine(url, pool_pre_ping=True)


@st.cache_data(ttl=3600)
def run_query(query: str) -> pd.DataFrame:
    engine = get_engine()
    return pd.read_sql(text(query), engine)
