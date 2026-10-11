from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils.text import slugify
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.accounts.permissions import IsAdminOrReadOnly
from apps.core.activity import log_activity

from .models import Category, CategoryChecklistItem, CategoryWeight, Dimension, Rule, validate_weights


class ChecklistItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = CategoryChecklistItem
        fields = ["id", "item", "obrigatorio", "tipo"]


class CategorySerializer(serializers.ModelSerializer):
    pesos = serializers.SerializerMethodField()
    checklist = ChecklistItemSerializer(many=True, read_only=True)

    class Meta:
        model = Category
        fields = ["id", "nome", "slug", "termos_busca", "cnaes", "osm_tags", "ativo", "pesos", "checklist"]
        read_only_fields = ["slug"]

    def get_pesos(self, obj):
        return obj.weights()

    def validate_termos_busca(self, value):
        return [t.strip() for t in value if isinstance(t, str) and t.strip()]

    def create(self, validated):
        validated["slug"] = slugify(validated["nome"])[:80]
        return super().create(validated)


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.prefetch_related("pesos", "checklist")
    serializer_class = CategorySerializer
    permission_classes = [IsAdminOrReadOnly]
    pagination_class = None
    http_method_names = ["get", "post", "patch", "put", "delete"]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("ativas"):
            qs = qs.filter(ativo=True)
        return qs

    @action(detail=True, methods=["put"])
    def weights(self, request, pk=None):
        category = self.get_object()
        try:
            weights = {k: float(v) for k, v in request.data.items()}
            validate_weights(weights)
        except (TypeError, ValueError) as exc:
            raise ValidationError({"pesos": "Valores numéricos esperados."}) from exc
        except DjangoValidationError as exc:
            raise ValidationError({"pesos": exc.messages}) from exc
        with transaction.atomic():
            for dim in Dimension:
                CategoryWeight.objects.update_or_create(
                    category=category, dimensao=dim.value, defaults={"peso": round(weights[dim.value], 3)}
                )
        log_activity(request.user, "pesos_alterados", category, pesos=weights)
        return Response(CategorySerializer(self.get_queryset().get(pk=category.pk)).data)

    @action(detail=True, methods=["post"])
    def checklist(self, request, pk=None):
        category = self.get_object()
        ser = ChecklistItemSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        ser.save(category=category)
        return Response(CategorySerializer(self.get_queryset().get(pk=category.pk)).data, status=201)

    @action(detail=True, methods=["delete"], url_path=r"checklist/(?P<item_id>\d+)")
    def delete_checklist_item(self, request, pk=None, item_id=None):
        category = self.get_object()
        category.checklist.filter(pk=item_id).delete()
        return Response(CategorySerializer(self.get_queryset().get(pk=category.pk)).data)


class RuleSerializer(serializers.ModelSerializer):
    dimensao_nome = serializers.CharField(source="get_dimensao_display", read_only=True)

    class Meta:
        model = Rule
        fields = ["id", "codigo", "dimensao", "dimensao_nome", "descricao", "severidade_padrao", "ativo"]
        read_only_fields = ["codigo", "dimensao", "descricao", "severidade_padrao"]


class RuleViewSet(viewsets.ModelViewSet):
    queryset = Rule.objects.all()
    serializer_class = RuleSerializer
    permission_classes = [IsAdminOrReadOnly]
    pagination_class = None
    http_method_names = ["get", "patch"]

    def list(self, request, *args, **kwargs):
        sync_rules()
        return super().list(request, *args, **kwargs)


def sync_rules():
    """Mantém a tabela `rule` alinhada ao catálogo em código, preservando o campo `ativo`."""
    from apps.audits.engine.rules import rule_catalog

    for item in rule_catalog():
        Rule.objects.update_or_create(
            codigo=item["codigo"],
            defaults={k: item[k] for k in ("dimensao", "descricao", "severidade_padrao")},
        )
