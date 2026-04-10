@echo off
cd /d "d:\agent-one"
start "" http://localhost:8501
streamlit run app.py --server.port 8501 --server.headless true
