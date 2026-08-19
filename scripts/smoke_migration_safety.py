#!/usr/bin/env python3
from verify_migration_safety import validate_sql

prefix = "BEGIN;\nCREATE TABLE IF NOT EXISTS vantaline.feature_migrations(version TEXT);\n"
suffix = "\nINSERT INTO vantaline.feature_migrations(version) VALUES ('test') ON CONFLICT DO NOTHING;\nCOMMIT;"

for statement in (
    "UPDATE users SET role='admin';",
    "UPDATE vantaline.users SET role='admin';",
    'UPDATE "vantaline"."users" SET role=\'admin\';',
    "DELETE FROM vantaline.users;",
    "ALTER TABLE vantaline.users DROP COLUMN role;",
    "DO $$ BEGIN EXECUTE 'DROP TABLE users'; END $$;",
):
    try:
        validate_sql(prefix + statement + suffix, "malicious-test")
    except ValueError:
        pass
    else:
        raise AssertionError(f"unsafe migration was accepted: {statement}")

validate_sql(prefix + "CREATE INDEX IF NOT EXISTS idx_test ON vantaline.feature_migrations(version);" + suffix, "safe-test")
print("migration safety adversarial smoke passed")
