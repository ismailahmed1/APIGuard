# Full prototype loop. Needs ANTHROPIC_API_KEY and the NEXSTOCK_* accounts in .env, and a
# saved evaluation (python scripts/evaluate_faults.py). Re-record from the repository root:
#   vhs docs/demo/apiguard-full-loop.tape
# The live generate call costs about $0.10.
Output docs/demo/apiguard-full-loop.mp4
Output docs/demo/apiguard-full-loop.gif

Require docker
Set Shell "bash"
Set FontSize 20
Set Width 1600
Set Height 900
Set Padding 24
Set Theme "Dracula"
Set WindowBar Colorful
Set TypingSpeed 25ms

Hide
Type `set +m; export PATH="$PWD/.venv/bin:$HOME/.docker/bin:$PATH" DOCKER_CLI_HINTS=false COMPOSE_FILE=apps/nexstock/compose.yaml PS1='$ '` Enter
Type "NEXSTOCK_FAULT= docker compose up --detach --wait api >/dev/null 2>&1; clear" Enter
Wait@180s /^\$$/
Show

Type "# APIGuard (SYSC 4907): Claude writes the tests once; APIGuard runs them without AI." Enter
Type "# NexStock runs in Docker with fixed seed data. 1. Generate tests for the Categories API:" Enter
Type "apiguard generate nexstock --tag Categories" Enter
Wait@300s /^\$$/
Sleep 4s
Type "head -c 700 suites/nexstock/$(cat suites/nexstock/LATEST)/tests.json; echo" Enter
Wait@10s /^\$$/
Sleep 5s

Type "clear" Enter
Type "# 2. Run the saved suite. The API key is removed: no AI model is used." Enter
Type "ANTHROPIC_API_KEY= apiguard run nexstock --label original" Enter
Wait@180s /^\$$/
Sleep 6s

Type "clear" Enter
Type "# 3. Seed fault F02: creating a category returns 200 instead of 201. Restart NexStock with it:" Enter
Type "NEXSTOCK_FAULT=F02-category-create-wrong-status docker compose up --detach --wait api 2>/dev/null" Enter
Wait@180s /^\$$/
Type "ANTHROPIC_API_KEY= apiguard run nexstock --label F02 >/dev/null; apiguard compare nexstock original F02" Enter
Wait@180s /^\$$/
Sleep 6s

Type "clear" Enter
Type "# 4. Full evaluation: 118-test suite (4 API areas) vs. Schemathesis, original app + 3 seeded faults" Enter
Type "python scripts/evaluate_faults.py --show" Enter
Wait@30s /^\$$/
Sleep 8s

Hide
Type "NEXSTOCK_FAULT= docker compose up --detach --wait api >/dev/null 2>&1" Enter
Wait@180s /^\$$/
