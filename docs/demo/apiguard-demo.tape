# Re-record from the repository root on a branch with #5 and #8:  vhs docs/demo/apiguard-demo.tape
Output docs/demo/apiguard-demo.mp4
Output docs/demo/apiguard-demo.gif

Require docker
Set Shell "bash"
Set FontSize 14
Set Width 1920
Set Height 1000
Set Padding 24
Set Theme "Dracula"
Set WindowBar Colorful
Set TypingSpeed 30ms

Hide
Type `export PATH="$PWD/.venv/bin:$HOME/.docker/bin:$PATH" DOCKER_CLI_HINTS=false PS1='$ '` Enter
Type "docker compose -f apps/nexstock/compose.yaml down --volumes >/dev/null 2>&1; clear" Enter
Wait@120s /^\$$/
Show

Type "# APIGuard: AI-assisted API testing and security monitoring (SYSC 4907)" Enter
Sleep 1s
Type "# 1. Start NexStock (pinned commit) with PostgreSQL and fixed seed data" Enter
Type "docker compose -f apps/nexstock/compose.yaml up --detach --wait api" Enter
Wait@180s /^\$$/
Sleep 2s

Type "# 2. Check the configuration, connectivity and OpenAPI specification" Enter
Type "apiguard check nexstock" Enter
Wait@60s /^\$$/
Sleep 3s

Type "clear" Enter
Type "# 3. Extract every operation: auth rules, parameters, request bodies and responses" Enter
Type "apiguard spec nexstock" Enter
Wait@60s /^\$$/
Sleep 10s

Type "clear" Enter
Type "# 4. Clear errors and exit codes when the application is down" Enter
Type "docker compose -f apps/nexstock/compose.yaml stop api" Enter
Wait@60s /^\$$/
Type `apiguard check nexstock; echo "exit code: $?"` Enter
Wait@60s /^\$$/
Sleep 3s

Type "# 5. Reset restores identical seed data; then the app is back" Enter
Type "docker compose -f apps/nexstock/compose.yaml run --rm reset" Enter
Wait@60s /^\$$/
Type "docker compose -f apps/nexstock/compose.yaml up --detach --wait api" Enter
Wait@120s /^\$$/
Type `apiguard check nexstock; echo "exit code: $?"` Enter
Wait@60s /^\$$/
Sleep 4s
