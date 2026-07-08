.PHONY: install install-dev init init-codex demo figure-plan-demo prompt-spec-demo status render validate test worker-once tmux-demo memory-plan clean

install:
	python -m pip install -e .

install-dev:
	python -m pip install -e '.[dev]'

init:
	python -m autopilot_nodekit init --workspace . --manifest examples/manifest.yml --config examples/config.shell.yml

init-codex:
	python -m autopilot_nodekit init --workspace . --manifest examples/manifest.yml --config examples/config.codex.yml --codex-native

figure-plan-demo: clean
	python -m autopilot_nodekit init --workspace . --manifest examples/manifest.yml --config examples/config.shell.yml --codex-native --force
	python -m autopilot_nodekit generate-figure-plan --workspace . --figures 3 --journal "Demo Journal"
	python -m autopilot_nodekit validate --workspace .
	python -m autopilot_nodekit status --workspace .

prompt-spec-demo: clean
	cp examples/project_prompt.figure_batch.md PROJECT_PROMPT.md
	python -m autopilot_nodekit smart-start --workspace . --prompt-file PROJECT_PROMPT.md --force-codex-native
	python -m autopilot_nodekit validate --workspace . --strict
	python -m autopilot_nodekit next-command --workspace .

demo: clean
	python -m autopilot_nodekit init --workspace . --manifest examples/manifest.yml --config examples/config.shell.yml --codex-native --force
	python -m autopilot_nodekit run-once --workspace . --worker-id demo-worker
	python -m autopilot_nodekit memory-plan --workspace . --task-id T002
	python -m autopilot_nodekit run-once --workspace . --worker-id demo-worker
	python -m autopilot_nodekit validate --workspace .
	python -m autopilot_nodekit status --workspace .

worker-once:
	python -m autopilot_nodekit run-once --workspace . --worker-id local-worker

status:
	python -m autopilot_nodekit status --workspace .

render:
	python -m autopilot_nodekit render --workspace .

validate:
	python -m autopilot_nodekit validate --workspace .

test:
	python -m compileall -q autopilot_nodekit tests
	python -m pytest -q

memory-plan:
	python -m autopilot_nodekit memory-plan --workspace . --task-id T002

background-doctor:
	python -m autopilot_nodekit background-doctor --workspace .

tmux-demo:
	bash scripts/tmux_start_worker.sh . local-worker 0

clean:
	rm -rf automation runs memory .autopilot-nodekit .pytest_cache PROJECT_PROMPT.md PROJECT_SPEC.yml PROJECT_SPEC.md PROJECT_SETUP.yml SETUP_REVIEW.md GOAL_CONTRACT.yml GOAL_CONTRACT.md TASK_REVIEW.md REQUIREMENTS_LOCK.md CODEX_GOAL.md CODEX_PROJECT_GOAL.md
