# 安装指南

## 快速安装

```bash
git clone https://github.com/conanxin/agent-loop.git
cd agent-loop
./scripts/install-all.sh
export PATH="$HOME/.agent-loop/bin:$PATH"
```

## 分步安装

### 仅安装工具

```bash
./scripts/install.sh
```

### 仅安装 Skills

```bash
./scripts/install-skills.sh
```

### 完整安装（工具 + Skills + 冒烟测试）

```bash
./scripts/install-all.sh
```

## 自定义路径

```bash
# 自定义 agent-loop 安装目录
export AGENT_LOOP_HOME=/opt/agent-loop
./scripts/install.sh

# 自定义 OpenClaw skills 目录
export OPENCLAW_SKILLS_DIR=/custom/openclaw/skills
./scripts/install-skills.sh

# 自定义 Hermes skills 目录
export HERMES_SKILLS_DIR=/custom/hermes/skills
./scripts/install-skills.sh
```

## 升级

```bash
cd ~/.agent-loop
git pull origin main
```

## 卸载

```bash
rm -rf ~/.agent-loop
# 从 ~/.bashrc 中移除 PATH 配置
```

## 验证安装

```bash
# 验证工具
agent-loop-init-goal test "Test goal"
agent-loop-show test

# 验证 OpenClaw skill
cat ${OPENCLAW_SKILLS_DIR:-$HOME/.openclaw/workspace/skills}/hermes-agent-loop/SKILL.md

# 验证 Hermes skill
cat ${HERMES_SKILLS_DIR:-$HOME/.hermes/skills}/openclaw-command-executor/SKILL.md

# 运行冒烟测试
./scripts/smoke-test.sh
```

## 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `AGENT_LOOP_HOME` | `~/.agent-loop` | agent-loop 安装目录 |
| `OPENCLAW_SKILLS_DIR` | `~/.openclaw/workspace/skills` | OpenClaw skills 目录 |
| `HERMES_SKILLS_DIR` | `~/.hermes/skills` | Hermes skills 目录 |

## 故障排除

### 工具未找到

```bash
export PATH="$HOME/.agent-loop/bin:$PATH"
source ~/.bashrc
```

### Skills 未生效

Skills 安装后可能需要重新加载 agent。检查文件是否存在：

```bash
ls -la ${OPENCLAW_SKILLS_DIR:-$HOME/.openclaw/workspace/skills}/hermes-agent-loop/
ls -la ${HERMES_SKILLS_DIR:-$HOME/.hermes/skills}/openclaw-command-executor/
```

### 冒烟测试失败

检查 `~/.agent-loop/bin/` 是否在 PATH 中，以及 Python3 是否可用。
