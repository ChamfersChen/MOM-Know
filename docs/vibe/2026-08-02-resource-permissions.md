# 资源共享权限细粒度化

## 目标

统一 Agent、Skill 和 KnowledgeBase 的共享权限解析，支持同一资源分别配置只读范围与管理范围，并让后端接口按 `none/read/manage` 统一校验。

## 范围

- 共享配置升级为 `version: 2`，包含 `read_scope` 与 `manage_scope`。
- 新增公共资源权限解析模块，消除三类资源重复的范围判断。
- KnowledgeBase 保留平台角色上限：普通用户最多只读，admin 可管理，superadmin 全局管理。
- Agent/Skill 保留现有资源能力边界，由公共权限结果和领域规则共同决定。
- 前端共享配置器支持分别设置读取范围与管理范围，并根据有效权限隐藏管理操作。
- KnowledgeBase 读取范围必填且包含创建者本人或所在部门；管理范围不得超出读取范围，前端保留全部选项并提示越界，保存时拒绝。历史越界 V2 配置按管理范围优先迁移。
- 旧配置兼容读取；历史 KnowledgeBase 共享默认迁移为原有管理语义，Agent/Skill 保留原有可见性语义。

## 非目标

- 不新增独立 ACL 数据表。
- 不实现同一权限下多种范围的组合选择；当前每个 scope 继续使用 `global/department/user` 三选一。
- 不改变内置 Agent/Skill、外部只读知识库等领域能力限制。

## 设计

```json
{
  "version": 2,
  "read_scope": {"access_level": "global", "department_ids": [], "user_uids": []},
  "manage_scope": {"access_level": "department", "department_ids": [1, 2], "user_uids": []}
}
```

管理权限天然包含读取权限，`manage_scope` 必须是 `read_scope` 的子集。KnowledgeBase 的 `read_scope` 不可为空，`manage_scope` 为空表示仅创建者与 superadmin 可管理；新建默认全局读取、管理范围为空。有效权限取所有者、superadmin、范围匹配和资源角色上限的交集，优先级为 `manage > read > none`。

公共模块提供：

- `normalize_permission_config`
- `scope_matches`
- `resolve_resource_permission`
- `require_resource_permission`

路由层只声明 `read` 或 `manage` 要求；资源加载和内置资源约束仍留在各自领域模块。

## 验收标准

- [x] 全局只读、指定部门管理的权限组合可正确保存、返回和执行。
- [x] owner/superadmin 为 manage；KnowledgeBase 普通用户不超过 read。
- [x] 未共享用户无法通过直接资源 ID 访问资源接口。
- [x] Agent、Skill、KnowledgeBase 使用同一公共权限解析器。
- [x] 只读用户前端不显示上传、编辑、删除、配置保存等管理入口。
- [x] 旧共享配置可读取且权限不意外扩大；迁移/兼容行为有测试覆盖。
- [x] Docker 环境内相关 unit/integration 测试、lint 和前端构建通过。

## Checklist

- [x] 后端公共权限模块与单元测试
- [x] 三类资源仓储/服务/路由接入
- [x] 前端 ShareConfigForm 和知识库/Agent/Skill 页面接入
- [x] changelog 更新
- [x] Docker 测试、lint 与人工审阅材料

## 验证记录

- 后端相关测试：`104 passed, 1 skipped`（补充新旧配置迁移、管理范围严格校验和权限回归测试）。
- 前端 ESLint、Ruff check/format、`git diff --check` 均通过。
- 前端生产构建通过；仅有已有的 Rolldown 注释与大 chunk 警告。
- 浏览器验证：新建知识库表单可独立开启“可管理范围”，默认部门模式，普通用户只读提示正确；未保存并已关闭。
- 截图：`docs/vibe/2026-08-02-resource-permission-selector.png`。
