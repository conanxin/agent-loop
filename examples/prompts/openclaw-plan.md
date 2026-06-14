---
title: OpenClaw Plan Prompt Example
---

# OpenClaw Plan Prompt

## 示例：添加用户认证

**用户输入**:
```
Add user authentication to my Express app
```

**OpenClaw 输出**:

```
BEGIN_OPENCLAW_DECISION
goal_id: auth-express-20260614
iteration: 1
decision: NEXT_COMMAND
requires_human_approval: true
reason: First step: inspect current codebase to determine where auth fits
next_expected_result: List of relevant files and current auth state (none/partial)
END_OPENCLAW_DECISION

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

## 关键规则

- **只输出一个** `BEGIN_HERMES_COMMAND`
- 不输出 inspect + implement 两个块
- 人类审核通过 `requires_human_approval` 控制
