"""
flake8 entry point. Always runs the postgres -> oracle checks (see
db_portability.checks.postgres_oracle): flake8 plugins don't have a natural
way to expose a --from/--to pair the way the `dbp-scan` CLI does, so this
runs the one pair most Django/Postgres shops need. Other pairs registered in
db_portability.checks can still be run through `dbp-scan --from --to`.
"""
from db_portability.checks.postgres_oracle import run as run_postgres_oracle


class PostgresPortabilityChecker:
    name = "db-portability"
    version = "0.1.1"

    def __init__(self, tree, filename="(none)"):
        self.tree = tree
        self.filename = filename

    def run(self):
        for lineno, col, message in run_postgres_oracle(self.tree):
            yield lineno, col, message, type(self)
