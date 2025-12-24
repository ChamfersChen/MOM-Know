from typing import Any, Annotated
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Union, Optional
from pydantic import BaseModel, Field

from mcp.server.fastmcp import Context, FastMCP
from typing import Any
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
import tempfile, os
from minio_tool.client import aupload_file_to_minio

# 中文字体支持
plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False


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
):
    if not data:
        raise ValueError("data 不能为空")

    df = pd.DataFrame(data)
    df["value"] = pd.to_numeric(df["value"], errors="coerce")

    n = len(df)

    # ⭐ 1. 更合理的柱宽（不要太细）
    bar_width = min(0.9, max(0.6, 12 / n))

    # ⭐ 2. 控制画布宽度（不要过宽）
    fig_width = max(7, 0.45)
    plt.figure(figsize=(fig_width, 5))

    ax = sns.barplot(
        data=df,
        x="category",
        y="value",
        hue="category",
        palette="colorblind", # tab10, deep, colorblind, pastel
        legend=False,
        errorbar=None,
    )

    # ⭐ 3. 设置柱宽 & 居中
    for bar in ax.patches:
        bar.set_width(bar_width)
        bar.set_x(bar.get_x() + (bar.get_width() - bar_width) / 2)

    # ⭐ 4. 压缩类目轴左右留白（非常关键）
    ax.margins(x=0.02)

    ax.set_title(title)
    ax.set_xlabel(axisXTitle)
    ax.set_ylabel(axisYTitle)

    # 数值标签
    max_value = df["value"].max()
    offset = max_value * 0.02 if max_value else 1

    for bar in ax.patches:
        h = bar.get_height()
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            h + offset,
            f"{int(h)}",
            ha="center",
            va="bottom",
            fontsize=9,
        )

    if n > 8:
        plt.xticks(rotation=30)

    plt.tight_layout()
        # ⭐ 关键：保存到临时文件
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        temp_path = f.name

    plt.savefig(temp_path, dpi=150)
    plt.close()

    with open(temp_path, 'rb') as file:
            image_bytes = file.read()
    # ⭐ 上传到 MinIO
    file_name = os.path.basename(temp_path)
    # bucket_name = os.environ.get("MINIO_BUCKET_NAME", "mcp-charts")
    bucket_name = "mcp-charts"
    url = await aupload_file_to_minio(bucket_name, file_name, image_bytes, ".png")

    os.remove(temp_path)
    ret = f"图片已经生成完毕，请使用`![图片描述]({url})`在文中插入图片。"
    return ret



@mcp.tool(
    name="generate_pie_chart",
    title="",
    description=
    "Generate a pie chart to show the proportion of parts, such as, market share and budget allocation.",
)
async def generate_pie_chart(
    title: Annotated[str, Field(description='Set the title of chart.')],
    data: Annotated[list[dict[str, Any]], Field(description='Data for pie chart, it should be an array of object contains a `category` field and a `value` field, such as [{"category": "A", "value": 10}, {"category": "B", "value": 20}]')]
):
    if not data:
        raise ValueError("data 不能为空")

    df = pd.DataFrame(data)
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    
    # 过滤掉值为0或NaN的数据
    df = df[df["value"] > 0].dropna()
    if len(df) == 0:
        raise ValueError("没有有效的正数数据")
    
    n = len(df)
    
    # 自适应设置图形大小
    fig_size = max(7, n * 0.4)  # 根据类别数量调整大小
    fig, ax = plt.subplots(figsize=(fig_size, fig_size))
    
    # 计算百分比
    total = df["value"].sum()
    percentages = df["value"] / total * 100
    
    colors = sns.color_palette("colorblind", n_colors=n)
    
    # 绘制饼图
    wedges, texts, autotexts = ax.pie(
        df["value"],
        labels=df["category"],
        autopct='%1.1f%%',
        colors=colors,
        startangle=90,
        textprops={'fontsize': 14},
        wedgeprops={'edgecolor': 'w', 'linewidth': 1.5},
        pctdistance=0.85
    )
    
    # 设置百分比标签样式
    for autotext in autotexts:
        autotext.set_color('black')
        autotext.set_fontweight('bold')
        autotext.set_fontsize(12)
    
    # 设置标题
    ax.set_title(title, fontsize=16, fontweight='bold', pad=20)
    
    # 确保图形是圆形
    ax.axis('equal')
    
    # # 添加图例
    # legend_labels = [f'{cat}: {val:,.0f}' for cat, val in zip(df["category"], df["value"])]
    # ax.legend(
    #     wedges,
    #     legend_labels,
    #     title="类别详情",
    #     loc="center left",
    #     bbox_to_anchor=(1, 0, 0.5, 1),
    #     fontsize=9
    # )
    
    plt.tight_layout()
    
    # 保存到临时文件
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        temp_path = f.name
    
    plt.savefig(temp_path, dpi=150, bbox_inches='tight')
    plt.close()
    
    # 读取文件
    with open(temp_path, 'rb') as file:
        image_bytes = file.read()
    
    # 上传到 MinIO
    file_name = os.path.basename(temp_path)
    bucket_name = "mcp-charts"
    url = await aupload_file_to_minio(bucket_name, file_name, image_bytes, ".png")
    
    os.remove(temp_path)
    ret = f"图片已经生成完毕，请使用`![图片描述]({url})`在文中插入图片。"
    return ret

# async def generate_pie_chart(
#     title: Annotated[str, Field(description='Set the title of chart.')],
#     data: Annotated[list[dict[str, Any]], Field(description='Data for pie chart, it should be an array of object contains a `category` field and a `value` field, such as [{"category": "A", "value": 10}, {"category": "B", "value": 20}]')]
# ):
#     """Search for information related to a query"""
#     sd = []
#     for d in data:
#         sd.append(f'\"{d['category']}\": {d['value']}')

#     return ('```mermaid\n'
#     f'pie title {title}\n'
#     '    ' + '\n    '.join(sd) +
#     '\n```'
#     )

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