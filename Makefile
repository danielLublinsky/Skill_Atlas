.PHONY: build check render test smoke m4-check clean

# Build graph.json from the live machine's manifests. Exit 1 from the script
# means "built, with findings" — that is a report, not a failure; only exit 2
# (build failed) stops make. Use `make check` to enforce the gate in CI.
build:
	@python3 scripts/build_graph.py; s=$$?; [ $$s -ne 2 ] || exit $$s

# Strict CI gate: fails on any dangling edge or broken reference (exit 1).
check:
	python3 scripts/build_graph.py --check

# Render atlas.html from graph.json.
render:
	python3 scripts/render.py

# Full unit suite against fixtures. Never touches the real ~/.claude.
test:
	bash tests/run_tests.sh

# Read-only structural assertions against the real machine (M1/M2/M5, §11.1–11.3).
smoke:
	python3 dev/smoke_live.py

# M4 is a manual procedure — this just prints it.
m4-check:
	@echo "M4 (auto-update) manual check:"
	@echo "  1. claude plugin marketplace add $(CURDIR)"
	@echo "  2. claude plugin install skill-atlas@skill-atlas"
	@echo "  3. Note 'generated_at' in \$$SKILL_ATLAS_HOME/graph.json (default ~/.claude/skill-atlas/)"
	@echo "  4. Toggle any entry in ~/.claude/settings.json enabledPlugins"
	@echo "  5. Start a new Claude Code session, then re-check graph.json:"
	@echo "     generated_at advanced and the toggled plugin's nodes flipped 'enabled'"
	@echo "  6. In-session: edit any SKILL.md -> \$$SKILL_ATLAS_HOME/graph.dirty appears;"
	@echo "     next SessionStart consumes it and rebuilds. Toggle the plugin back."

clean:
	rm -f graph.json atlas.html
