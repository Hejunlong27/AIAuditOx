# 审小牛 MCP 接口

## 地址

本机默认地址：

```text
http://127.0.0.1:11436/mcp
```

健康检查：

```text
GET http://127.0.0.1:11436/health
```

服务默认只监听 `127.0.0.1`。如需给其他本机 Agent 使用，可设置：

```powershell
$env:AUDITOX_MCP_PORT = '11436'
$env:AUDITOX_MCP_TOKEN = '<local-token>'
```

设置 Token 后，MCP 请求必须携带：

```text
Authorization: Bearer <local-token>
```

Token 只通过环境变量提供，不写入仓库。

## 协议

接口支持 MCP JSON-RPC 2.0 的：

- `initialize`
- `ping`
- `tools/list`
- `tools/call`

工具结果同时返回文本内容与 `structuredContent`。

## 当前工具

| 工具 | 用途 |
| --- | --- |
| `auditox_harness_status` | 查看 Harness、模型网关、技能源和 Runtime 状态 |
| `auditox_skill_list` | 列出本地技能库 |
| `auditox_skill_read` | 读取指定 `SKILL.md` |
| `auditox_runtime_health` | 检查旧版 AuditOx Runtime |
| `auditox_project_list` | 列出审计项目 |
| `auditox_workpaper_trace` | 返回任务、计划、产物、审批和留痕 |
| `auditox_export_workpaper` | 生成可复核底稿 |
| `auditox_guided_stage` | 推进引导审计阶段 |

## 外部 Agent 配置示例

```json
{
  "mcpServers": {
    "auditox": {
      "type": "streamable-http",
      "url": "http://127.0.0.1:11436/mcp"
    }
  }
}
```

外部 Agent 只能通过本机回环地址访问；审小牛不会主动把客户数据发送到外部服务。
