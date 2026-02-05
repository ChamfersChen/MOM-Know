import os
import random
import httpx

from langchain.tools import tool
from pydantic import BaseModel, Field
import requests

from src.storage import global_variable
from src.utils import logger
from src.storage.ext_redis import redis_client
from .service import (
    get_user_info_by_username,
    get_order_total_info_by_factory_id,
)



MOM_API_BASE_URL = os.environ.get("MOM_API_BASE_URL")
# MOM_LOGIN_USERNAME = os.environ.get("MOM_LOGIN_USERNAME")




@tool(name_or_callable="fetch_mom_system_info", description="需要操作MOM系统前需要先查看当前MOM系统信息, 为操作MOM系统提供必要的信息")
def fetch_mom_organization_info() -> str:
    extras = fetch_mom_organization_info.extras
    current_username = extras.get('current_username')
    try:
        user_info = get_user_info_by_username(current_username)
        data = user_info['data']
        user_info = data['userInfo']
        factories_info = data['factoriesInfo']
        factories_info_list = [f"工厂名称: {factory.get("label")}, 工厂ID: {factory.get('value')}" for factory in factories_info]
        return "\n---\n".join(factories_info_list)

    except Exception as e:
        return f"获取用户信息失败: {e}"

def random_bigint():
    return random.randint(10**18, 10**19 - 1)

class SystemNewsModel(BaseModel):
    """MOM系统添加系统公告的参数模型"""
    title: str = Field(description="公告标题", example="关于公开招聘工作人员的公告")
    content: str = Field(description="公告内容", example="为进一步加强人才队伍建设，适应发展需要，经研究决定，面向社会公开招聘工作人员。现将有关事项公告如下：...")
    start_time: str = Field(description="公告发布开始时间 (精确到天, 不需要具体时间点)", example="2025-02-11")
    end_time: str = Field(description="公告发布结束时间 (精确到天, 不需要具体时间点)", example="2025-12-31")
    factory_id: str = Field(description="添加公告的工厂ID")

@tool(name_or_callable="add_mom_system_news", description="在获得MOM系统信息完成之后执行，为MOM系统添加系统公告", args_schema=SystemNewsModel)
def add_mom_system_news_tool(title: str, content: str, start_time: str, end_time: str, factory_id: str) -> str:
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
    extras = fetch_mom_organization_info.extras
    current_username = extras.get('current_username')
    try:
        user_info = get_user_info_by_username(current_username)
        data = user_info['data']
        user_info = data['userInfo']
        username = user_info.get("username")
        tenant_id = user_info.get("tenantId")
        factories_info = data['factoriesInfo']
        factories_id = [factory.get('value') for factory in factories_info]
        if factory_id not in factories_id:
            return "组织ID不在当前用户系统中，无法添加公告。请确认组织ID是否正确，或者当前用户是否有权限添加公告。"
        body = {
                "id": random_bigint(),
                "title": title,
                "content": content,
                "startTime": start_time,
                "endTime": end_time,
                "organizationId": factory_id,
                "createBy": username,
                "createTime": "",
                "updateBy": username,
                "updateTime": "",
                "delFlag": None,
                "tenantId": tenant_id,
                "status": "",
                "organizationIds": None
            }
        
        token = redis_client.get(username)
        headers = {
                "Authorization": "Bearer "+token,
                "Accept": "application/json, text/plain, */*",
                "skipToken": "True",
                "TENANT-ID": str(tenant_id)
            }
    except Exception as e:
        return f"获取用户信息失败: {e}"

    try:
        resp = requests.post("http://8.130.128.22:32518/admin/sysNews", headers=headers,json=body)
        # resp = requests.post(MOM_API_BASE_URL+"/admin/sysNews", headers=headers,json=body)
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

class FactoryIdModel(BaseModel):
    factory_id: str = Field(description="添加公告的工厂ID")

@tool(name_or_callable="get_order_statistic_info", description="在获得MOM系统信息完成之后执行，根据工厂ID获得订单统计信息", args_schema=FactoryIdModel)
def get_order_statistic_info(factory_id: str) -> str:
    """根据工厂ID获得订单统计信息"""
    # 添加系统公告
    extras = fetch_mom_organization_info.extras
    current_username = extras.get('current_username')
    try:
        user_info = get_user_info_by_username(current_username)
        data = user_info['data']
        user_info = data['userInfo']
        username = user_info.get("username")
        tenant_id = user_info.get("tenantId")
        factories_info = data['factoriesInfo']
        factories_id = [factory.get('value') for factory in factories_info]
        if factory_id not in factories_id:
            return "组织ID不在当前用户系统中，无法添加公告。请确认组织ID是否正确，或者当前用户是否有权限添加公告。"
        
        token = redis_client.get(username)
        headers = {
                "Authorization": "Bearer "+token,
                "Accept": "application/json, text/plain, */*",
                "skipToken": "True",
                "TENANT-ID": str(tenant_id)
            }
    except Exception as e:
        return f"获取用户信息失败: {e}"

    try:
        result = get_order_total_info_by_factory_id(factory_id, headers)
        order_data = result['data']

        order_info = "当前工厂的订单统计信息:\n"

        orderNum = order_data['orderNum']
        orderDiff = float(order_data['orderDiff'])
        order_info += f"订单总数: {orderNum}单; 较上周: {"增加" if orderDiff >= 0 else "减少"} {orderDiff}单\n"

        orderFulfillRate = order_data['orderFulfillRate']
        order_info += f"订单总交付率: {orderFulfillRate}%\n"

        orderShipmentNum = order_data['orderShipmentNum']
        orderShipmentDiff = float(order_data['orderShipmentDiff'])
        order_info += f"订单总发货数: {orderShipmentNum}个; 较上周: {"增加" if orderShipmentDiff >= 0 else "减少"} {orderShipmentDiff}个\n"

        pendingTaskNum = order_data['pendingTaskNum']
        pendingTaskDiff = float(order_data['pendingTaskDiff'])
        order_info += f"待完成生产任务数: {pendingTaskNum}个; 较上周: {"增加" if pendingTaskDiff >= 0 else "减少"} {pendingTaskDiff}%\n"

        taskCompletionRate = order_data['taskCompletionRate']
        order_info += f"任务总完成率: {taskCompletionRate}%\n"

        productInventoryNum = order_data['productInventoryNum']
        productInventoryDiff = float(order_data['productInventoryDiff'])
        order_info += f"成品库存数量: {productInventoryNum}个; 较上周: {"增加" if productInventoryDiff >= 0 else "减少"} {productInventoryDiff}个\n"

        warhouseWarningNum = order_data['warhouseWarningNum']
        warhouseWarningDiff = float(order_data['warhouseWarningDiff'])
        order_info += f"原材库存预警: {warhouseWarningNum}种; 较上周: {"增加" if warhouseWarningDiff >= 0 else "减少"} {warhouseWarningDiff}%\n"

        badNum = order_data['badNum']
        badDiff = float(order_data['badDiff'])
        order_info += f"不良上报总数: {badNum}个; 较上周: {"增加" if badDiff >= 0 else "减少"} {badDiff}%\n"
        return order_info

    except httpx.HTTPStatusError as e:
        logger.debug(str(e))
        return f"获得订单统计信息失败！{str(e)}"



def get_mom_tools() -> list:
    return [
        fetch_mom_organization_info,
        add_mom_system_news_tool,
        add_mom_system_schedule_tool,
        get_order_statistic_info,
    ]