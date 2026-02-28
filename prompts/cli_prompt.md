# CLI Main Prompt (telefd2d MCP execution)

你是 `telefd2d` 主执行 CLI。请完成“方案决策 + MCP 落地 + 验证 + 文档更新”闭环。

## Objective
- 让 AI 能通过 MCP 工具稳定调用 telefd2d 正演流程，并可读取结构化输出。

## Constraints
1. 数值求解核心行为保持兼容，不修改物理含义。
2. 继续保持 compute/postprocess 解耦。
3. 先计划后执行，每步必须有 AC。
4. 失败时记录 RCA，并执行至少一次替代尝试。
5. 最大子代理并发为 2。

## Workflow
1. 技术方案评估：判断 MCP 是否优于纯脚本/纯 REST，并记录决策依据。
2. 实现 MCP 服务：
   - `telefd2d_summarize_project`
   - `telefd2d_run_forward_case`
   - `telefd2d_get_case_report`
   - `telefd2d_list_cases`
3. 提供 MCP 启动入口与 smoke test 脚本。
4. 运行 smoke test，产出一组输出目录并验证元数据文件。
5. 更新 README 与 docs，给出安装、启动、工具调用示例和验收标准。

## Deliverables
- `src/telefd2d_mcp/server.py`
- `scripts/run_mcp_server.py`
- `scripts/mcp_smoke_test.py`
- `docs/mcp_decision.md`
- `docs/mcp_integration.md`
- `README.md`, `README_EN.md`, `README_ZH.md`
- `docs/workflow_plan.md`

## Acceptance Criteria
- AC-M1: `python scripts/mcp_smoke_test.py --backend baseline` 成功。
- AC-M2: smoke output 目录包含 `compute_metadata.json` 与 `run_metadata.json`。
- AC-M3: MCP 文档中有可复制执行的启动命令和至少一个工具调用示例。
- AC-M4: README 家族文档都包含 MCP 快速开始入口。
