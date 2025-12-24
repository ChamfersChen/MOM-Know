#!/bin/bash

# run mcp
cd mcp_server
uv run mcp run -t streamable-http echarts_server.py:mcp

# Start the MinerU API
# export MINERU_MODEL_SOURCE=local 
set MINERU_MODEL_SOURCE=local
uv run mineru-api --host 0.0.0.0 --port 30001

# Start the UI
pnpm run dev

# Start the main server
uv run --no-dev uvicorn server.main:app --host 0.0.0.0 --port 5050