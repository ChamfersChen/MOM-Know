import dotenv
from mcp.server.fastmcp import FastMCP

from src.service.echarts import register_echarts_tools
from src.service.weather import register_weather_tools
dotenv.load_dotenv()


mcp = FastMCP(
    name="echarts tools",
    instructions="Tool for echarts.",
    port=8001,
    host="127.0.0.1",
)
# register_echarts_tools(mcp)
register_weather_tools(mcp)