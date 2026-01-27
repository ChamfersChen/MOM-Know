import pymysql
from pymysql.cursors import DictCursor

connection = pymysql.connect(
    host="localhost",
    user="root",
    password="root123",
    database="mom",
    port=3306,
    charset="utf8mb4",
    cursorclass=DictCursor,
    connect_timeout=10,
    read_timeout=60,  # 增加读取超时
    write_timeout=30,
    autocommit=True,  # 自动提交
)

def test_connection() -> bool:
    """测试连接是否有效"""
    try:
        if connection and connection.open:
            # 执行简单查询测试连接
            with connection.cursor() as cursor:
                cursor.execute("select count(*) from mom_mes_wms.raw_material_issuance_voucher mmw_r join mom.sys_tenant st where mmw_r.tenant_id = st.id ;")
                res = cursor.fetchone()
                print(res)
            return True
    except Exception as _:
        pass
    return False


test_connection()