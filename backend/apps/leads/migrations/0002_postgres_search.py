"""Extensões pg_trgm/unaccent e índice trigram para busca aproximada de nomes (TRD 2.2 / 5.2).

Só roda no PostgreSQL; no SQLite de desenvolvimento a deduplicação usa a mesma
métrica em Python (apps.core.text.trigram_similarity).
"""
from django.db import migrations

FORWARD = [
    "CREATE EXTENSION IF NOT EXISTS pg_trgm",
    "CREATE EXTENSION IF NOT EXISTS unaccent",
    "CREATE INDEX IF NOT EXISTS company_nome_trgm ON leads_company USING gin (nome_normalizado gin_trgm_ops)",
]
BACKWARD = ["DROP INDEX IF EXISTS company_nome_trgm"]


def run(statements):
    def apply(apps, schema_editor):
        if schema_editor.connection.vendor != "postgresql":
            return
        for sql in statements:
            schema_editor.execute(sql)

    return apply


class Migration(migrations.Migration):
    dependencies = [("leads", "0001_initial")]

    operations = [migrations.RunPython(run(FORWARD), run(BACKWARD))]
