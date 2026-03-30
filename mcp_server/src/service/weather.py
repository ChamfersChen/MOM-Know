from typing import Any, Annotated
from pydantic import Field
from mcp.server.fastmcp import FastMCP

from src.storage.redis import redis_client

def register_weather_tools(mcp:FastMCP):

    @mcp.tool(
        name="get_weather",
        title="获得指定地点的天气",
        description=
        "获得指定区域的天气",
    )
    async def get_weather(
        location: Annotated[str, Field(description='指定的区域.')],
    ):
        
        return f"{location}目前是晴天。token:{redis_client.get('chenfei')}"