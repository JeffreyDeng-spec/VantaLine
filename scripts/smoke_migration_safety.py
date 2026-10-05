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

from local_inspection_service.storage.label_summary_schema import migration_sql

audited = migration_sql()
validate_sql(audited, "exact-derived-invalidation")
for tampered in (
    audited.replace("DELETE FROM \"vantaline\".label_run_projection", "DELETE FROM \"vantaline\".users"),
    audited.replace(" WHERE id = OLD.id", ""),
    audited.replace(" WHERE id = NEW.id", ""),
    audited.replace(" WHERE id IN (OLD.id, NEW.id)", ""),
    audited.replace("SECURITY DEFINER", "SECURITY INVOKER"),
    audited.replace("SET search_path = pg_catalog", "SET search_path = public"),
    audited.replace("vantaline", "other_schema"),
    audited.replace("END;", "EXECUTE 'DELETE FROM vantaline.users'; END;", 1),
    audited.replace("COMMIT;", "DELETE FROM vantaline.users; COMMIT;"),
    prefix + "/*" + audited + "*/ DELETE FROM vantaline.users;" + suffix,
    prefix + "SELECT $payload$" + audited + "$payload$; DELETE FROM vantaline.users;" + suffix,
):
    try:
        validate_sql(tampered, "tampered-derived-invalidation")
    except ValueError:
        pass
    else:
        raise AssertionError("Changed derived-invalidation migration was accepted")
print("exact derived-cache migration exception and mutation rejection passed")
