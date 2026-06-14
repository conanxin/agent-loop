---
title: OpenClaw Judge-Path Prompt Example
---

# OpenClaw Judge-Path Prompt

## 示例：评审 Hermes 报告

**Hermes 通知**:
```
HERMES_STATUS: REPORT_WRITTEN
HERMES_REPORT_PATH: ~/.agent-loop/goals/auth-express-20260614/hermes-reports/001.md
```

**OpenClaw 输入**:
```
/skill hermes-agent-loop judge-path

report_path: ~/.agent-loop/goals/auth-express-20260614/hermes-reports/001.md
```

## 关键规则

- judge prompt 必须分两行：
  1. `/skill hermes-agent-loop judge-path`
  2. `report_path: <absolute-path>`
- 不要写成 `/skill hermes-agent-loop judge-path <path>`
- OpenClaw 读取文件后进行 15 点格式检查
- 根据报告状态输出 `BEGIN_OPENCLAW_DECISION`
