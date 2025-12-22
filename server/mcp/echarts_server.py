from typing import Any, Annotated
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Union, Optional
from pydantic import BaseModel, Field

from mcp.server.fastmcp import Context, FastMCP

class PieParams(BaseModel):
    title: str = Field(..., description="Set the title of chart.")
    data: list[dict[str, Any]] = Field(..., description='Data for pie chart, it should be an array of object contains a `category` field and a `value` field, such as [{"category": "A", "value": 10}, {"category": "B", "value": 20}]')

# Pass lifespan to server
mcp = FastMCP(
    name="echarts tools",
    instructions=r"""
Tool for echarts.
""".strip(),
    # lifespan=app_lifespan,
    port=8001,
)


@mcp.tool(
    name="generate_bar_chart",
    title="",
    description=
    "Generate a horizontal bar chart to show data for numerical comparisions among different categories, such as, compairing categorical data and for horizontal comparisons.",
)
async def generate_bar_chart(
    title: Annotated[str, Field(description='Set the title of chart.')],
    data: Annotated[list[dict[str, Any]], Field(description='Data for bar chart, it should be an array of object contains a `category` field and a `value` field, such as [{"category": "A", "value": 10}, {"category": "B", "value": 20}]')],
    axisXTitle: Annotated[str, Field(description='Set the title of X axis.')],
    axisYTitle: Annotated[str, Field(description='Set the title of Y axis.')],
) -> str:
    """Search for information related to a query"""
    x_value, y_value, x_axis = [], [], []
    for d in data:
        x_value.append(d['category'])
        y_value.append(d['value'])

    for a in x_value:
        x_axis.append(f'\"{a}\"')
    

    return ('```mermaid\n'
    'xychart-beta \n'
    f'    title \"{title}\"\n'
    f'    x-axis \"{axisXTitle}\" [{", ".join(x_axis)}]\n'
    f'    y-axis \"{axisYTitle}\" 0 --> {max(y_value)+5}\n'
    f'    bar {y_value}\n'
    '```\n'
    )


@mcp.tool(
    name="generate_pie_chart",
    title="",
    description=
    "Generate a pie chart to show the proportion of parts, such as, market share and budget allocation.",
)
async def generate_pie_chart(
    # params: PieParams
    title: Annotated[str, Field(description='Set the title of chart.')],
    data: Annotated[list[dict[str, Any]], Field(description='Data for pie chart, it should be an array of object contains a `category` field and a `value` field, such as [{"category": "A", "value": 10}, {"category": "B", "value": 20}]')]
):
    """Search for information related to a query"""
    sd = []
    for d in data:
        sd.append(f'\"{d['category']}\": {d['value']}')

    return ('```mermaid\n'
    f'pie title {title}\n'
    '    ' + '\n    '.join(sd) +
    '\n```'
    )

@mcp.tool(
    name="generate_line_chart",
    title="",
    description=
    "Generate a line chart to show the trends over time, such as, the ratio of Apple computer sales to Apple's profits changed from 2000 to 2020.",
)
async def generate_line_chart(
    title: Annotated[str, Field(description='Set the title of chart.')],
    data: Annotated[list[dict[str, Any]], Field(description='Data for line chart, it should be an array of objects, each object contains a `time` field and a `value` field, such as, [{ time: "2015", value: 23 }, { time: "2016", value: 32 }].')],
    axisXTitle: Annotated[str, Field(description='Set the x-axis title of chart.')],
    axisYTitle: Annotated[str, Field(description='Set the y-axis title of chart.')],
) -> str:
    """Search for information related to a query"""
    x_value, y_value, x_axis = [], [], []
    for d in data:
        x_value.append(d['time'])
        y_value.append(d['value'])

    for a in x_value:
        x_axis.append(f'\"{a}\"')
    

    return ('```mermaid\n'
    'xychart-beta \n'
    f'    title \"{title}\"\n'
    f'    x-axis \"{axisXTitle}\" [{", ".join(x_axis)}]\n'
    f'    y-axis \"{axisYTitle}\" 0 --> {max(y_value)+5}\n'
    f'    line {y_value}\n'
    '```\n'
    )

# uv run mcp run -t streamable-http echarts_server.py:mcp