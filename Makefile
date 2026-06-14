.PHONY: validate smoke install install-skills

validate:
	@echo "=== Validating scripts ==="
	bash -n scripts/install.sh
	bash -n scripts/install-skills.sh
	bash -n scripts/install-all.sh
	bash -n scripts/smoke-test.sh
	bash -n bin/agent-loop-init-goal
	bash -n bin/agent-loop-set-state
	bash -n bin/agent-loop-show
	bash -n bin/agent-loop-relay
	@echo "=== Checking required files ==="
	@test -f README.md
	@test -f README.zh-CN.md
	@test -f LICENSE
	@test -f CHANGELOG.md
	@test -f .gitignore
	@test -f docs/INSTALL.md
	@test -f docs/AGENT_SKILLS.md
	@test -f docs/SPEC.md
	@test -f docs/STATE_MACHINE.md
	@test -f docs/MANUAL_RELAY_WORKFLOW.md
	@test -f docs/SCHEMAS.md
	@test -f docs/SAFETY_BOUNDARIES.md
	@test -f docs/TROUBLESHOOTING.md
	@echo "=== Checking for secrets ==="
	! grep -R "BOT_TOKEN" . --exclude-dir=.git --exclude-dir=docs --exclude=Makefile || (echo "WARNING: BOT_TOKEN found"; exit 1)
	! grep -R "TELEGRAM_TOKEN" . --exclude-dir=.git --exclude-dir=docs --exclude=Makefile || (echo "WARNING: TELEGRAM_TOKEN found"; exit 1)
	! grep -R "ghp_" . --exclude-dir=.git --exclude-dir=docs --exclude=Makefile || (echo "WARNING: ghp_ found"; exit 1)
	! grep -R "xoxb-" . --exclude-dir=.git --exclude-dir=docs --exclude=Makefile || (echo "WARNING: xoxb- found"; exit 1)
	@echo "=== Validation PASSED ==="

validate-skills:
	@echo "=== Validating skills ==="
	@bash -n scripts/validate-skills.sh
	@scripts/validate-skills.sh

smoke:
	./scripts/smoke-test.sh

install:
	./scripts/install.sh

install-skills:
	./scripts/install-skills.sh
