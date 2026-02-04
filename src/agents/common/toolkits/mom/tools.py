import os
import random
import httpx

from langchain.tools import tool
from pydantic import BaseModel, Field
import requests

from src.storage import global_variable
from src.utils import logger



MOM_API_BASE_URL = os.environ.get("MOM_API_BASE_URL")
# MOM_LOGIN_USERNAME = os.environ.get("MOM_LOGIN_USERNAME")


class SystemNewsModel(BaseModel):
    """MOM系统添加系统公告的参数模型"""
    title: str = Field(description="公告标题", example="关于公开招聘工作人员的公告")
    content: str = Field(description="公告内容", example="为进一步加强人才队伍建设，适应发展需要，经研究决定，面向社会公开招聘工作人员。现将有关事项公告如下：...")
    start_time: str = Field(description="公告发布开始时间 (精确到天, 不需要具体时间点)", example="2025-02-11")
    end_time: str = Field(description="公告发布结束时间 (精确到天, 不需要具体时间点)", example="2025-12-31")
    organization_id: str = Field(description="添加公告的组织ID")


@tool(name_or_callable="fetch_mom_system_info", description="需要操作MOM系统前需要先查看当前MOM系统信息, 为操作MOM系统提供必要的信息")
def fetch_mom_organization_info() -> str:
    mom_user_info:dict = global_variable.get("mom_user_info")
    organizations = mom_user_info.get("organizations")
    organizations_info = [f"组织名称: {organization.get("name")}, 组织ID: {organization.get('id')}" for organization in organizations if organization.get("type")=="1"]
    return "\n---\n".join(organizations_info)
    

def random_bigint():
    return random.randint(10**18, 10**19 - 1)

@tool(name_or_callable="add_mom_system_news", description="在获得MOM系统信息完成之后执行，为MOM系统添加系统公告", args_schema=SystemNewsModel)
def add_mom_system_news_tool(title: str, content: str, start_time: str, end_time: str, organization_id: str) -> str:
    """为MOM系统添加系统公告

    Parameters
    ----------
    title : str
        公告标题
    content : str
        公告内容
    start_time : str
        公告发布开始时间
    end_time : str
        公告发布结束时间
    organization_id : str
        添加公告的组织ID

    Returns
    -------
    str
        添加系统公告后的提示信息
    """
    # 添加系统公告
    mom_user_info:dict = global_variable.get("mom_user_info")
    username = mom_user_info.get("username")
    tenant_id = mom_user_info.get("tenant_id")
    token = mom_user_info.get("token")
    organizations = mom_user_info.get("organizations")
    organizations_ids = [str(organization.get('id')) for organization in organizations if organization.get("type")=="1"]

    if organization_id not in organizations_ids:
        return "组织ID不在当前用户系统中，无法添加公告。请确认组织ID是否正确，或者当前用户是否有权限添加公告。"

    body = {
            "id": random_bigint(),
            "title": title,
            "content": content,
            "startTime": start_time,
            "endTime": end_time,
            "organizationId": organization_id,
            "createBy": username,
            "createTime": "",
            "updateBy": username,
            "updateTime": "",
            "delFlag": None,
            "tenantId": tenant_id,
            "status": "",
            "organizationIds": None
        }
    headers = {
            "Authorization": "Bearer "+token,
            "Accept": "application/json, text/plain, */*",
            "skipToken": "True",
            "TENANT-ID": str(tenant_id)
        }
    logger.debug(headers)

    logger.debug(body)
    try:
        resp = requests.post(MOM_API_BASE_URL+"/admin/sysNews", headers=headers,
            json=body
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        logger.debug(str(e))
        return f"创建系统公告失败！{str(e)}"

    return f"创建系统公告成功！"


class SystemScheduleModel(BaseModel):
    """MOM系统添加系统公告的参数模型"""
    title: str = Field(description="日程标题", example="关于天津项目的进度沟通会")
    description: str = Field(description="日程具体描述", example="同步项目当前核心进展。讨论并解决当前遇到的主要问题或障碍。明确下一阶段的重点任务与分工。...")
    start_time: str = Field(description="日程开始时间 (精确到具体时间点)", example="2025-12-01 14:00:00")
    end_time: str = Field(description="日程结束时间 (精确到具体时间点)", example="2025-12-01 15:30:00")

@tool(name_or_callable="add_mom_system_schedule", description="在获得MOM系统信息完成之后执行，为MOM系统添加日程信息", args_schema=SystemScheduleModel)
def add_mom_system_schedule_tool(title: str, description: str, start_time: str, end_time: str) -> str:
    mom_user_info:dict = global_variable.get("mom_user_info")
    tenant_id = mom_user_info.get("tenant_id")
    token = mom_user_info.get("token")

    body = {
            "title": title,
            "description": description,
            "startTime": start_time,
            "endTime": end_time,
        }
    headers = {
            "Authorization": "Bearer " + token,
            "Accept": "application/json, text/plain, */*",
            "skipToken": "True",
            "TENANT-ID": str(tenant_id)
        }
    try:
        resp = requests.post(MOM_API_BASE_URL+"/admin/schedule", headers=headers,
            json=body
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        logger.debug(str(e))
        return f"创建日程失败！{str(e)}"

    return f"创建日程成功！"