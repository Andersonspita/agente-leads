from django_otp.plugins.otp_totp.models import TOTPDevice
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.activity import log_activity

from .models import User
from .permissions import IsAdmin


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, min_length=10)
    has_2fa = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "role", "is_active", "password", "has_2fa", "last_login"]
        read_only_fields = ["last_login"]

    def get_has_2fa(self, obj):
        return TOTPDevice.objects.filter(user=obj, confirmed=True).exists()

    def create(self, validated):
        password = validated.pop("password", None)
        user = User.objects.create_user(password=password, **validated)
        return user

    def update(self, instance, validated):
        password = validated.pop("password", None)
        for k, v in validated.items():
            setattr(instance, k, v)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class UserViewSet(viewsets.ModelViewSet):
    """Gestão das contas internas (somente Administrador)."""

    queryset = User.objects.order_by("email")
    serializer_class = UserSerializer
    permission_classes = [IsAdmin]
    http_method_names = ["get", "post", "patch"]

    @action(detail=True, methods=["post"])
    def reset_2fa(self, request, pk=None):
        user = self.get_object()
        TOTPDevice.objects.filter(user=user).delete()
        log_activity(request.user, "2fa_resetado", user)
        return Response({"ok": True})
