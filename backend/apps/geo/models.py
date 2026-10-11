from django.db import models

from apps.core.text import normalize


class Municipality(models.Model):
    codigo_ibge = models.CharField(max_length=7, primary_key=True)
    nome = models.CharField(max_length=80)
    uf = models.CharField(max_length=2, db_index=True)
    nome_normalizado = models.CharField(max_length=80, db_index=True)

    class Meta:
        ordering = ["nome"]
        verbose_name = "município"

    def save(self, *args, **kwargs):
        self.nome_normalizado = normalize(self.nome)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.nome}/{self.uf}"
