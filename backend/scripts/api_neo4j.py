# -*- coding: utf-8 -*-
"""
API 调用关系图谱 —— Neo4j 版本
================================
与 api_graph.py (networkx 版) 节点/边模型完全一致, 逻辑对齐, 可复现同一份图。

节点标签:
    :API      {endpoint, method, description, params, body, response_note}
    :Field    {name, description}
    :Category {name}
    :Scenario {name, description}

关系类型:
    (:API)-[:PRODUCES]->(:Field)
    (:API)-[:REQUIRES]->(:Field)
    (:API)-[:BELONGS_TO]->(:Category)
    (:API)-[:STEP_OF {order:int}]->(:Scenario)
    (:API)-[:DEPENDS_ON {via_field:string}]->(:API)   -- 派生关系, 由 rebuild_dependencies() 重算

依赖推导规则 (与 networkx 版一致):
    若 A REQUIRES 字段 F, B PRODUCES 字段 F, 则 (A)-[:DEPENDS_ON]->(B)

运行前置条件:
    pip install neo4j
    本地或远程启动一个 Neo4j 实例, 例如:
        docker run -d --name neo4j-demo -p7474:7474 -p7687:7687 \
            -e NEO4J_AUTH=neo4j/your_password neo4j:5

    然后修改下面 main() 里的 URI / USER / PASSWORD。
"""

from typing import Optional
from neo4j import GraphDatabase
from workflows import step

# -*- coding: utf-8 -*-
"""
将 Neo4j "场景调用链" 查询结果转换为 AI 可读的 Markdown 文档。

对应查询:
    MATCH (a:API)-[step:STEP_OF]->(s:Scenario {name: $scenarioName})
    OPTIONAL MATCH (a)-[:REQUIRES]->(req:Field)
    OPTIONAL MATCH (a)-[:PRODUCES]->(prod:Field)
    WITH a, step, collect(DISTINCT req.name) AS required_fields,
                  collect(DISTINCT prod.name) AS produced_fields
    RETURN a.endpoint AS endpoint, a.method AS method, a.description AS description,
           step.order AS call_order, a.params AS params, a.body AS body,
           required_fields, produced_fields
    ORDER BY step.order;

核心设计点: 不只是把每条记录罗列出来, 而是额外做一次"字段溯源" ——
对每个接口 required_fields 里的每个字段, 反查它是在前面哪一步被 produced 出来的,
生成类似 "organization_id (来自 Step 1)" 这样的说明。这对 AI 理解调用链的
因果关系至关重要, 比单纯堆砌 JSON 更容易被正确使用。
"""

import json
from typing import Any, Iterable, Union


def _parse_json_field(value: Union[str, None]) -> Any:
    """params / body 在库里存的是 JSON 字符串 (也可能是 null), 统一解析成 dict/None"""
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value  # 解析失败就原样返回, 避免整个函数崩掉


def _normalize_record(rec: Any) -> dict:
    """
    兼容两种输入:
      1) neo4j 官方驱动返回的 Record 对象 (有 .data() 方法)
      2) 已经是普通 dict (比如你把结果自己转成了 list[dict])
    """
    if hasattr(rec, "data"):
        return rec.data()
    return dict(rec)


def _fmt_field_list(fields: Iterable[str]) -> str:
    fields = [f for f in fields if f]  # 过滤掉 collect() 里可能出现的 null
    return ", ".join(f"`{f}`" for f in fields) if fields else "无"


def scenario_result_to_markdown(scenario_name: str, records: Iterable[Any]) -> str:
    """
    将 Cypher 查询返回的记录集转换为结构化 Markdown。

    参数:
        scenario_name: 场景名称, 如 "工单排程流程"
        records: 查询结果, 支持 neo4j.Record 列表 或 list[dict]，
                 且必须已经按 call_order 升序排列 (对应查询里的 ORDER BY step.order)

    返回:
        Markdown 字符串
    """
    steps = [_normalize_record(r) for r in records]
    if not steps:
        return f"# 业务场景: {scenario_name}\n\n(未查询到任何调用步骤, 请确认场景名称是否正确)\n"

    # ---- 第一遍: 建立 "字段名 -> 产出它的 step 序号" 索引, 用于后面做字段溯源 ----
    field_source_step = {}
    for s in steps:
        for f in s.get("produced_fields") or []:
            if f and f not in field_source_step:
                field_source_step[f] = s["call_order"]

    lines = []
    lines.append(f"# 业务场景调用流程: {scenario_name}\n")
    lines.append(f"共 {len(steps)} 个接口调用步骤, 按顺序执行。\n")

    # ---- 调用顺序总览 (给 AI 一个快速概览, 不用逐段读详情就能知道整体流程) ----
    lines.append("## 调用顺序总览\n")
    for s in steps:
        lines.append(f"{s['call_order']}. `{s['method']} {s['endpoint']}` — {s.get('description') or '(无描述)'}")
    lines.append("")

    # ---- 详细步骤 ----
    lines.append("## 详细步骤\n")
    visited_steps = set()
    for s in steps:
        if s["call_order"] not in visited_steps:
            lines.append(f"### Step {s['call_order']}\n")
            visited_steps.add(s["call_order"])

        lines.append(f"- **接口**: `{s['method']}: {s['endpoint']}`")
        lines.append(f"- **描述**: {s.get('description') or '无'}")

        params = _parse_json_field(s.get("params"))
        body = _parse_json_field(s.get("body"))
        lines.append(f"- **Params**: {json.dumps(params, ensure_ascii=False) if params else '无'}")
        lines.append(f"- **Body**: {json.dumps(body, ensure_ascii=False) if body else '无'}")

        # 依赖字段: 标注每个字段具体来自哪一步, 这是给 AI 用的关键信息
        required = [f for f in (s.get("required_fields") or []) if f]
        if required:
            req_desc = []
            for f in required:
                src = field_source_step.get(f)
                if src is not None and src != s["call_order"]:
                    req_desc.append(f"`{f}` (来自 Step {src})")
                else:
                    req_desc.append(f"`{f}` (来源未知, 需人工确认)")
            lines.append(f"- **依赖字段 (REQUIRES)**: {', '.join(req_desc)}")
        else:
            lines.append("- **依赖字段 (REQUIRES)**: 无, 该接口可独立调用")

        lines.append(f"- **产出字段 (PRODUCES)**: {_fmt_field_list(s.get('produced_fields') or [])}")
        lines.append("---")

    # ---- 给 AI 的执行提示: 明确告诉它这是一个严格顺序执行的调用链 ----
    lines.append("## 执行说明\n")
    lines.append(
        "以上步骤必须按 Step 序号从小到大依次调用；每一步"
        "『依赖字段』中标注『来自 Step N』的字段，其值必须取自 Step N 响应中的对应字段，"
        "不能凭空构造或从其他来源获取。"
    )

    return "\n".join(lines)


class Neo4jApiGraph:
    def __init__(self, uri: str, user: str, password: str):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self._init_constraints()

    def close(self):
        self.driver.close()

    # ================= 初始化约束 (保证唯一性 + 加速查询) =================

    def _init_constraints(self):
        stmts = [
            "CREATE CONSTRAINT api_endpoint_unique IF NOT EXISTS FOR (a:API) REQUIRE a.endpoint IS UNIQUE",
            "CREATE CONSTRAINT field_name_unique IF NOT EXISTS FOR (f:Field) REQUIRE f.name IS UNIQUE",
            "CREATE CONSTRAINT category_name_unique IF NOT EXISTS FOR (c:Category) REQUIRE c.name IS UNIQUE",
            "CREATE CONSTRAINT scenario_name_unique IF NOT EXISTS FOR (s:Scenario) REQUIRE s.name IS UNIQUE",
        ]
        with self.driver.session() as session:
            for stmt in stmts:
                session.run(stmt)

    # ================= CREATE =================

    def add_api(
        self,
        category: list,
        endpoint: str,
        method: str,
        description: str,
        params=None,
        body=None,
        response_note: str = "",
        produces: Optional[list] = None,
        requires: Optional[list] = None,
    ):
        produces = produces or []
        requires = requires or []

        def _tx(tx):
            tx.run(
                """
                MERGE (a:API {endpoint: $endpoint})
                SET a.method = $method,
                    a.description = $description,
                    a.params = $params,
                    a.body = $body,
                    a.response_note = $response_note
            """,
                endpoint=endpoint,
                method=method,
                description=description,
                params=_to_storable(params),
                body=_to_storable(body),
                response_note=response_note,
            )

            for cat in category:
                tx.run(
                    """
                    MERGE (c:Category {name: $cat})
                    WITH c
                    MATCH (a:API {endpoint: $endpoint})
                    MERGE (a)-[:BELONGS_TO]->(c)
                """,
                    cat=cat,
                    endpoint=endpoint,
                )

            for f in produces:
                tx.run(
                    """
                    MERGE (f:Field {name: $f})
                    WITH f
                    MATCH (a:API {endpoint: $endpoint})
                    MERGE (a)-[:PRODUCES]->(f)
                """,
                    f=f,
                    endpoint=endpoint,
                )

            for f in requires:
                tx.run(
                    """
                    MERGE (f:Field {name: $f})
                    WITH f
                    MATCH (a:API {endpoint: $endpoint})
                    MERGE (a)-[:REQUIRES]->(f)
                """,
                    f=f,
                    endpoint=endpoint,
                )

        with self.driver.session() as session:
            session.execute_write(_tx)

    def add_scenario(self, name: str, description: str, steps: list):
        """steps: [(endpoint, order), ...]"""
        import pdb

        pdb.set_trace()

        def _tx(tx):
            tx.run(
                "MERGE (s:Scenario {name: $name}) SET s.description = $description", name=name, description=description
            )
            for endpoint, order in steps:
                res = tx.run("MATCH (a:API {endpoint: $endpoint}) RETURN a", endpoint=endpoint).single()
                if res is None:
                    raise ValueError(f"接口不存在, 请先 add_api: {endpoint}")
                tx.run(
                    """
                    MATCH (a:API {endpoint: $endpoint}), (s:Scenario {name: $name})
                    MERGE (a)-[r:STEP_OF]->(s)
                    SET r.order = $order
                """,
                    endpoint=endpoint,
                    name=name,
                    order=order,
                )

        with self.driver.session() as session:
            session.execute_write(_tx)

    def rebuild_dependencies(self):
        """
        清空旧的 DEPENDS_ON 关系, 按 REQUIRES + PRODUCES 重新推导。
        每次新增/修改接口的 produces/requires 后调用一次。
        """

        def _tx(tx):
            tx.run("MATCH (:API)-[r:DEPENDS_ON]->(:API) DELETE r")
            tx.run("""
                MATCH (a:API)-[:REQUIRES]->(f:Field)<-[:PRODUCES]-(b:API)
                WHERE a <> b
                MERGE (a)-[dep:DEPENDS_ON]->(b)
                SET dep.via_field = f.name
            """)

        with self.driver.session() as session:
            session.execute_write(_tx)

    # ================= UPDATE =================

    def update_api(self, endpoint: str, **fields):
        """更新接口普通属性 (description/params/body/response_note/method)"""
        if not fields:
            return
        storable = {k: _to_storable(v) for k, v in fields.items()}
        set_clause = ", ".join(f"a.{k} = ${k}" for k in storable)
        with self.driver.session() as session:
            session.run(
                f"MATCH (a:API {{endpoint: $endpoint}}) SET {set_clause}",
                endpoint=endpoint,
                **storable,
            )

    def update_api_io(self, endpoint: str, produces: Optional[list] = None, requires: Optional[list] = None):
        """整体重设某接口的 produces/requires, 然后自动重新推导依赖"""

        def _tx(tx):
            tx.run(
                """
                MATCH (a:API {endpoint: $endpoint})-[r:PRODUCES]->(:Field)
                DELETE r
            """,
                endpoint=endpoint,
            )
            tx.run(
                """
                MATCH (a:API {endpoint: $endpoint})-[r:REQUIRES]->(:Field)
                DELETE r
            """,
                endpoint=endpoint,
            )
            for f in produces or []:
                tx.run(
                    """
                    MERGE (f:Field {name: $f})
                    WITH f
                    MATCH (a:API {endpoint: $endpoint})
                    MERGE (a)-[:PRODUCES]->(f)
                """,
                    f=f,
                    endpoint=endpoint,
                )
            for f in requires or []:
                tx.run(
                    """
                    MERGE (f:Field {name: $f})
                    WITH f
                    MATCH (a:API {endpoint: $endpoint})
                    MERGE (a)-[:REQUIRES]->(f)
                """,
                    f=f,
                    endpoint=endpoint,
                )

        with self.driver.session() as session:
            session.execute_write(_tx)
        self.rebuild_dependencies()

    # ================= DELETE =================

    def delete_api(self, endpoint: str):
        with self.driver.session() as session:
            session.run("MATCH (a:API {endpoint: $endpoint}) DETACH DELETE a", endpoint=endpoint)
        self.rebuild_dependencies()

    def delete_field(self, name: str):
        with self.driver.session() as session:
            session.run("MATCH (f:Field {name: $name}) DETACH DELETE f", name=name)
        self.rebuild_dependencies()

    def delete_scenario(self, name: str):
        with self.driver.session() as session:
            session.run("MATCH (s:Scenario {name: $name}) DETACH DELETE s", name=name)

    # ================= QUERY =================

    def get_api(self, endpoint: str) -> dict:
        with self.driver.session() as session:
            rec = session.run("MATCH (a:API {endpoint: $endpoint}) RETURN a", endpoint=endpoint).single()
            return dict(rec["a"]) if rec else {}

    def get_apis_by_category(self, category: str) -> list:
        with self.driver.session() as session:
            res = session.run(
                """
                MATCH (a:API)-[:BELONGS_TO]->(:Category {name: $category})
                RETURN a.endpoint AS endpoint
            """,
                category=category,
            )
            return [r["endpoint"] for r in res]

    def get_dependencies(self, endpoint: str) -> list:
        """该接口直接依赖哪些接口"""
        with self.driver.session() as session:
            res = session.run(
                """
                MATCH (a:API {endpoint: $endpoint})-[dep:DEPENDS_ON]->(b:API)
                RETURN b.endpoint AS depends_on, dep.via_field AS via_field
            """,
                endpoint=endpoint,
            )
            return [dict(r) for r in res]

    def get_dependents(self, endpoint: str) -> list:
        """哪些接口依赖了该接口"""
        with self.driver.session() as session:
            res = session.run(
                """
                MATCH (a:API)-[dep:DEPENDS_ON]->(b:API {endpoint: $endpoint})
                RETURN a.endpoint AS dependent, dep.via_field AS via_field
            """,
                endpoint=endpoint,
            )
            return [dict(r) for r in res]

    def get_call_chain(self, endpoint: str) -> list:
        """
        计算调用某接口需要的完整前置调用链 (从最上游到目标接口, 拓扑序)。
        实现方式: 先用变长路径拿到所有可达的 DEPENDS_ON 子图, 再在 Python 侧拓扑排序,
        与 networkx 版逻辑保持一致, 避免大图递归查询的复杂 Cypher。
        """
        import networkx as nx

        with self.driver.session() as session:
            res = session.run(
                """
                MATCH p = (start:API {endpoint: $endpoint})-[:DEPENDS_ON*0..]->(a:API)
                UNWIND relationships(p) AS rel
                RETURN DISTINCT startNode(rel).endpoint AS src, endNode(rel).endpoint AS dst
            """,
                endpoint=endpoint,
            )
            edges = [(r["src"], r["dst"]) for r in res]

        sub = nx.DiGraph()
        sub.add_node(endpoint)
        sub.add_edges_from(edges)
        order = list(reversed(list(nx.topological_sort(sub))))
        return order

    def get_scenario_steps(self, scenario_name: str) -> list:
        with self.driver.session() as session:
            res = session.run(
                """
                MATCH (a:API)-[r:STEP_OF]->(:Scenario {name: $name})
                RETURN a.endpoint AS endpoint, r.order AS order
                ORDER BY r.order
            """,
                name=scenario_name,
            )
            return [r["endpoint"] for r in res]

    def get_with_scenario(self, scenario_name: str) -> list:
        with self.driver.session() as session:
            res = session.run(
                """
                MATCH (a:API)-[step:STEP_OF]->(s:Scenario {name: $scenarioName})
                OPTIONAL MATCH (a)-[:REQUIRES]->(req:Field)
                OPTIONAL MATCH (a)-[:PRODUCES]->(prod:Field)
                WITH a, step, collect(DISTINCT req.name) AS required_fields, collect(DISTINCT prod.name) AS produced_fields
                RETURN a.endpoint      AS endpoint,
                    a.method        AS method,
                    a.description   AS description,
                    step.order      AS call_order,
                    a.params        AS params,
                    a.body          AS body,
                    required_fields,
                    produced_fields
                ORDER BY step.order;
            """,
                scenarioName=scenario_name,
            )
            return [dict(r) for r in res]

    def clear_all(self):
        """清空整个图谱 (慎用)"""
        with self.driver.session() as session:
            session.run("""
                MATCH (n)
                WHERE n:API OR n:Field OR n:Category OR n:Scenario
                DETACH DELETE n;     
            """)
        self.rebuild_dependencies()


def _to_storable(value):
    """Neo4j 属性不支持嵌套 dict, 复杂结构 (params/body) 统一存成 JSON 字符串"""
    import json

    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return value


# ======================================================================
# 演示: 与 api_graph.py 完全对齐的建图 + CRUD + 查询流程
# ======================================================================
def main():
    URI = "bolt://localhost:17687"
    USER = "neo4j"
    PASSWORD = "0123456789"  # 改成你自己的密码
    jsonl_path = "./test_apis.jsonl"
    scenarios_filepath = "test_scenarios.json"

    graph = Neo4jApiGraph(URI, USER, PASSWORD)

    try:
        # graph.clear_all()  # 清空图谱, 重新建图

        # with open(jsonl_path, "r", encoding="utf-8") as f:
        #     for line_no, line in enumerate(f, start=1):
        #         line = line.strip()
        #         if not line:
        #             continue
        #         try:
        #             record = json.loads(line)
        #             graph.add_api(
        #                 category=record.get("category") or [],
        #                 endpoint=record["endpoint"],
        #                 method=record["method"],
        #                 description=record.get("description") or "",
        #                 params=record.get("params"),
        #                 body=record.get("body"),
        #                 response_note=record.get("response_note") or "",
        #                 produces=record.get("produces") or [],
        #                 requires=record.get("requires") or [],
        #             )
        #         except json.JSONDecodeError as e:
        #             raise ValueError(f"第 {line_no} 行 JSON 解析失败: {e}\n原始内容: {line}")

        # graph.rebuild_dependencies()

        # for scenario_name, scenario in json.load(open(scenarios_filepath, "r", encoding="utf-8")).items():
        #     graph.add_scenario(
        #         name=scenario_name,
        #         description=scenario.get("description") or "",
        #         steps=[s.split(";") for s in scenario.get("steps") or []],
        #     )
        # graph.add_scenario(
        #     name="工单排程流程",
        #     description="工单排程流程的完整链路",
        #     steps=[
        #         ("admin/modelFactory/organization/list", 1),
        #         ("meswms/orderForAi/unproducedOrders", 2),
        #         ("meswms/orderForAi/getScheduleInfo", 3),
        #         ("meswms/orderForAi/createSchedule", 4),
        #     ],
        # )

        scenario_name = "工单修改删除流程"
        records = graph.get_with_scenario(scenario_name)
        md = scenario_result_to_markdown(scenario_name, records)
        print(md)

        # print("=== 查询: admin/order/update 的完整前置调用链 ===")
        # print(graph.get_call_chain("admin/order/update"))

        # print("\n=== 查询: admin/order/info 直接依赖谁 ===")
        # print(graph.get_dependencies("admin/order/info"))

        # print("\n=== 查询: organization/list 有哪些接口依赖它 ===")
        # print(graph.get_dependents("admin/modelFactory/organization/list"))

        # print("\n=== 查询: order 分类下有哪些接口 ===")
        # print(graph.get_apis_by_category("order"))

        # print("\n=== 查询: '订单处理流程' 场景的调用顺序 ===")
        # print(graph.get_scenario_steps("订单处理流程"))

        # # ---------- UPDATE ----------
        # graph.update_api("admin/order/info", description="获取订单详情(v2, 增加分页)")
        # graph.update_api_io("admin/order/info",
        #                      produces=["order_id", "order_status", "order_amount"],
        #                      requires=["organization_id"])
        # print("\n=== 更新后: admin/order/info 详情 ===")
        # print(graph.get_api("admin/order/info"))

        # # ---------- DELETE ----------
        # graph.delete_api("admin/order/update")
        # print("\n=== 删除 admin/order/update 后, order 分类接口 ===")
        # print(graph.get_apis_by_category("order"))

    finally:
        graph.close()


if __name__ == "__main__":
    main()
