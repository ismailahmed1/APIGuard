#!/bin/sh
# Make seed.sql: the tables that the app creates at startup, and two users.
# Run from the repository root only when the pinned commit changes, and commit the new seed.sql.
# The passwords are local test values; put them in .env as BANKING_*_PASSWORD.
set -eu
COMPOSE="docker compose -f apps/banking/compose.yaml"
: > apps/banking/seed.sql
$COMPOSE down --volumes
$COMPOSE up --detach --wait --build api
$COMPOSE exec -T api python - <<'PY'
from passlib.context import CryptContext
import pymysql

hash_ = CryptContext(schemes=["bcrypt"]).hash
users = [
    ("apiguard-admin", "APIGuard Admin", "Admin-Local-Test-1", "ADMIN"),
    ("apiguard-user", "APIGuard Customer", "User-Local-Test-1", "USER"),
]
db = pymysql.connect(host="mysql", user="banking", password="banking", database="banking")
with db.cursor() as cursor:
    for username, name, password, role in users:
        cursor.execute(
            "INSERT INTO users (username, name, password, role, status, created_at)"
            " VALUES (%s, %s, %s, %s, 'ACTIVE', '2026-11-28 00:00:00')",
            (username, name, hash_(password), role),
        )
db.commit()
PY
$COMPOSE exec -T mysql mysqldump -ubanking -pbanking --no-tablespaces --skip-dump-date banking \
  > apps/banking/seed.sql
$COMPOSE down --volumes
