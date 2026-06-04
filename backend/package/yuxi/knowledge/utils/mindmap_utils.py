"""思维导图工具函数。"""

import json
import textwrap
from typing import Any

from fastapi import HTTPException

from yuxi import config, knowledge_base
from yuxi.models import select_model
from yuxi.repositories.knowledge_base_repository import KnowledgeBaseRepository
from yuxi.utils import logger

MINDMAP_SYSTEM_PROMPT = """你是一个专业的知识整理助手。

你的任务是分析用户提供的文件列表，生成一个层次分明的思维导图结构。

**核心规则：每个文件名只能出现一次！不允许重复！**

要求：
1. 思维导图要有清晰的层级结构（2-4层）
2. 根节点是知识库名称
3. 第一层是主要分类（如：技术文档、规章制度、数据资源等）
4. 第二层是子分类
5. **叶子节点必须是具体的文件名称**
6. **每个文件名在整个思维导图中只能出现一次，不得重复！**
7. 如果一个文件可能属于多个分类，只选择最合适的一个分类放置
8. 使用合适的emoji图标增强可读性
9. 返回JSON格式，遵循以下结构：

```json
{
  "content": "知识库名称",
  "children": [
    {
      "content": "🎯 主分类1",
      "children": [
        {
          "content": "子分类1.1",
          "children": [
            {"content": "文件名1.txt", "children": []},
            {"content": "文件名2.pdf", "children": []}
          ]
        }
      ]
    },
    {
      "content": "💻 主分类2",
      "children": [
        {"content": "文件名3.docx", "children": []},
        {"content": "文件名4.md", "children": []}
      ]
    }
  ]
}
```

**重要约束：**
- 每个文件名在整个JSON中只能出现一次
- 不要按多个维度分类导致文件重复
- 选择最主要、最合适的分类维度
- 每个叶子节点的children必须是空数组[]
- 分类名称要简洁明了
- 使用emoji增强视觉效果
"""


def build_database_file_list(files: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "file_id": file_id,
            "filename": file_info.get("filename", ""),
            "type": file_info.get("type", ""),
            "status": file_info.get("status", ""),
            "created_at": file_info.get("created_at", ""),
        }
        for file_id, file_info in files.items()
    ]


def collect_mindmap_files(all_files: dict[str, dict[str, Any]], file_ids: list[str]) -> list[dict[str, str]]:
    return [
        {
            "filename": all_files[file_id].get("filename", ""),
            "type": all_files[file_id].get("type", ""),
        }
        for file_id in file_ids
        if file_id in all_files
    ]


def build_mindmap_user_message(db_name: str, files_info: list[dict[str, str]], user_prompt: str = "") -> str:
    files_text = "\n".join([f"- {file_info['filename']} ({file_info['type']})" for file_info in files_info])
    return textwrap.dedent(f"""请为知识库\"{db_name}\"生成思维导图结构。

        文件列表（共{len(files_info)}个文件）：
        {files_text}

        {f"用户补充说明：{user_prompt}" if user_prompt else ""}

        **重要提醒：**
        1. 这个知识库共有{len(files_info)}个文件
        2. 每个文件名只能在思维导图中出现一次
        3. 不要让同一个文件出现在多个分类下
        4. 为每个文件选择最合适的唯一分类

        请生成合理的思维导图结构。""")


def parse_mindmap_content(content: str) -> dict[str, Any]:
    if "```json" in content:
        json_start = content.find("```json") + 7
        json_end = content.find("```", json_start)
        content = content[json_start:json_end].strip()
    elif "```" in content:
        json_start = content.find("```") + 3
        json_end = content.find("```", json_start)
        content = content[json_start:json_end].strip()

    mindmap_data = json.loads(content)
    if not isinstance(mindmap_data, dict) or "content" not in mindmap_data:
        raise ValueError("思维导图结构不正确")
    return mindmap_data


async def get_mindmap_database_files(kb_id: str) -> dict[str, Any]:
    db_info = await knowledge_base.get_database_info(kb_id)
    if not db_info:
        raise HTTPException(status_code=404, detail=f"知识库 {kb_id} 不存在")

    file_list = build_database_file_list(db_info.get("files", {}))
    return {
        "message": "success",
        "kb_id": kb_id,
        "slug": kb_id,
        "db_name": db_info.get("name", ""),
        "files": file_list,
        "total": len(file_list),
    }


async def generate_database_mindmap(
    kb_id: str, file_ids: list[str] | None = None, user_prompt: str = ""
) -> dict[str, Any]:
    db_info = await knowledge_base.get_database_info(kb_id)
    if not db_info:
        raise HTTPException(status_code=404, detail=f"知识库 {kb_id} 不存在")

    db_name = db_info.get("name", "知识库")
    all_files = db_info.get("files", {})
    selected_file_ids = list(file_ids or all_files.keys())
    if not selected_file_ids:
        raise HTTPException(status_code=400, detail="知识库中没有文件")

    original_count = len(selected_file_ids)
    if len(selected_file_ids) > 20:
        selected_file_ids = selected_file_ids[:20]
        logger.info(f"文件数量超过限制，已从{original_count}个文件中选择前20个文件生成思维导图")

    files_info = collect_mindmap_files(all_files, selected_file_ids)
    if not files_info:
        raise HTTPException(status_code=400, detail="选择的文件不存在")

    logger.info(f"开始生成思维导图，知识库: {db_name}, 文件数量: {len(files_info)}")

    model = select_model(model_spec=config.default_model)
    messages = [
        {"role": "system", "content": MINDMAP_SYSTEM_PROMPT},
        {"role": "user", "content": build_mindmap_user_message(db_name, files_info, user_prompt)},
    ]
    response = await model.call(messages, stream=False)
    content = response.content if hasattr(response, "content") else str(response)

    try:
        mindmap_data = parse_mindmap_content(content)
    except ValueError as e:
        logger.error(f"AI返回的JSON解析失败: {e}, 原始内容: {content}")
        raise HTTPException(status_code=500, detail=f"AI返回格式错误: {str(e)}") from e

    logger.info("思维导图生成成功")

    try:
        await KnowledgeBaseRepository().update(kb_id, {"mindmap": mindmap_data})
        logger.info(f"思维导图已保存到知识库: {kb_id}")
    except Exception as save_error:
        logger.error(f"保存思维导图失败: {save_error}")

    return {
        "message": "success",
        "mindmap": mindmap_data,
        "kb_id": kb_id,
        "slug": kb_id,
        "db_name": db_name,
        "file_count": len(files_info),
        "original_file_count": original_count,
        "truncated": len(files_info) < original_count,
    }


async def get_mindmap_databases_overview(uid: str) -> dict[str, Any]:
    databases = await knowledge_base.get_databases_by_uid(uid)
    db_list = []
    for db_info in databases.get("databases", []):
        kb_id = db_info.get("kb_id") or db_info.get("slug")
        if not kb_id:
            continue

        detail_info = await knowledge_base.get_database_info(kb_id)
        file_count = len(detail_info.get("files", {})) if detail_info else 0
        db_list.append(
            {
                "kb_id": kb_id,
                "slug": kb_id,
                "name": db_info.get("name", ""),
                "description": db_info.get("description", ""),
                "kb_type": db_info.get("kb_type", ""),
                "file_count": file_count,
            }
        )

    return {"message": "success", "databases": db_list, "total": len(db_list)}


async def get_database_mindmap_data(kb_id: str) -> dict[str, Any]:
    kb = await KnowledgeBaseRepository().get_by_kb_id(kb_id)
    if kb is None:
        raise HTTPException(status_code=404, detail=f"知识库 {kb_id} 不存在")

    return {
        "message": "success",
        "mindmap": kb.mindmap,
        "kb_id": kb_id,
        "slug": kb_id,
        "db_name": kb.name,
    }
