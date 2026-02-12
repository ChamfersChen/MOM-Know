import os
import requests

MOM_API_BASE_URL = os.environ.get("MOM_API_BASE_URL")
def get_user_info_by_username(username: str) -> dict:
    """
    根据用户名获取用户信息
    """
    # response = requests.get(MOM_API_BASE_URL+f"/admin/user/getUserInfoToAI/{username}")
    response = requests.get(MOM_API_BASE_URL+f"/admin/user/getUserInfoToAI/{username}")
    response.raise_for_status()
    return response.json()

def get_order_total_info_by_factory_id(factory_id: str, headers=None) -> dict:
    """
    根据组织ID获取订单总数信息
    """
    response = requests.get(
        MOM_API_BASE_URL+"/meswms/index/getOrderInfo",
        params={'organizationIds': factory_id},
        headers=headers
    )
    response.raise_for_status()
    return response.json()




if __name__ == "__main__":
    print(get_user_info_by_username("chenfei"))
    headers = {
        "Authorization": "Bearer be2a44e6-0388-4176-a123-939ff46be4c8",
        "TENANT-ID": "1955078213888319490",
        "skipToken": "True"
    }
    print(get_order_total_info_by_factory_id("1955093964007350273 ", headers))
