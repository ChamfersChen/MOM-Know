import asyncio, json
# from src.knowledge import graph_base


file_path = "./test_database_meta.json"
databases_meta = json.load(open(file_path, "r", encoding="utf-8"))

tuple_jsonl = []
db_id2h = {}
for database_info in databases_meta:
    h = {
        "name": database_info["name"],
        "database_name": database_info["name"],
        "description": database_info["description"]

    }
    db_id2h[database_info["db_id"]] = h
    for table_id, table_info in database_info["tables"].items():
        if not table_info['is_choose']:
            continue
        t = {
            "name": table_info["tablename"],
            "description": table_info["total_description"],
            "database_name": database_info["name"],
            "table_name": table_info["tablename"],
            "table_description": table_info["description"],
        }
        tuple_jsonl.append({"h": h, "t": t, "r": "Table2Column"})
 
for database_info in databases_meta:
    for related_db_id in database_info["related_db_ids"]:
        t = db_id2h[related_db_id]
        tuple_jsonl.append({"h": h, "t": t, "r": "Table2Table"})

import ipdb; ipdb.set_trace()
# graph_base.create_graph_database("sql_neo4j")
# asyncio.run(graph_base.database_meta_add_entity(file_path))

