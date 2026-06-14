---
title: Hermes Command Execution Example
---

# Hermes Command Execution

## 示例：执行验证命令

**接收到的命令**:
```
BEGIN_HERMES_COMMAND
goal_id: auth-express-20260614
iteration: 1
command_type: inspect
objective: Map current project structure and identify auth-related files
context: Express app, unknown auth status
working_directory: .
instructions:
  1. List project root files and directory structure
  2. Check package.json for existing auth dependencies
  3. Search for existing auth middleware or user models
  4. Check for existing session/JWT configuration
validation: Provide a clear summary of current auth state
report_back: File tree, relevant files list, current auth status, recommended approach
stop_conditions: If no package.json or not an Express app, report BLOCKED
END_HERMES_COMMAND
```

## Hermes 执行规则

1. **只执行** instructions 中列出的步骤
2. **不扩大范围**（不运行 `npm test` 或 `npm build`）
3. **停止** 在验证通过后
4. 生成 **canonical report**（11 字段）
5. Telegram 只发送 **2 行通知**

## 生成的报告

```
BEGIN_HERMES_REPORT
goal_id: auth-express-20260614
iteration: 1
status: PASS
summary: No existing auth found. Express app with standard structure.
changed_files: none
commands_run: ls -la, cat package.json, grep -r "auth\|passport\|jwt" --include="*.js" .
validation_result: Confirmed: no auth middleware, no user models, no session config
commit: none
report_path: ~/.agent-loop/goals/auth-express-20260614/hermes-reports/001.md
issues: none
recommendation: Implement passport-local strategy with express-session
END_HERMES_REPORT
```

## Telegram 通知

```
HERMES_STATUS: REPORT_WRITTEN
HERMES_REPORT_PATH: ~/.agent-loop/goals/auth-express-20260614/hermes-reports/001.md
```
