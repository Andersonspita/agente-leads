from django.db.models import Case, IntegerField, Value, When
from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.core.text import normalize

from .models import Municipality


class MunicipalitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Municipality
        fields = ["codigo_ibge", "nome", "uf"]


@api_view(["GET"])
def municipalities(request):
    """Autocomplete de cidade validado contra a tabela do IBGE (RF02)."""
    q = normalize(request.query_params.get("q", ""))
    uf = request.query_params.get("uf", "").upper()
    qs = Municipality.objects.all()
    if uf:
        qs = qs.filter(uf=uf)
    if q:
        qs = qs.filter(nome_normalizado__contains=q).annotate(
            starts=Case(When(nome_normalizado__startswith=q, then=Value(0)), default=Value(1),
                        output_field=IntegerField())
        ).order_by("starts", "nome")
    return Response(MunicipalitySerializer(qs[:20], many=True).data)
