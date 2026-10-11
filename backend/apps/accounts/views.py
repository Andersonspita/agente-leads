import io

import qrcode
import qrcode.image.svg
from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django_otp import login as otp_login
from django_otp.plugins.otp_totp.models import TOTPDevice
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from apps.core.activity import log_activity

from .models import User
from .permissions import user_is_verified


class LoginThrottle(AnonRateThrottle):
    rate = "20/min"


def user_payload(request):
    user = request.user
    if not user.is_authenticated:
        return {"authenticated": False}
    has_device = TOTPDevice.objects.filter(user=user, confirmed=True).exists()
    verified = user_is_verified(user) if settings.REQUIRE_2FA else True
    return {
        "authenticated": True,
        "verified": verified,
        "require_2fa": settings.REQUIRE_2FA,
        "has_2fa": has_device,
        "setup_required": settings.REQUIRE_2FA and not has_device,
        "user": {"id": user.pk, "email": user.email, "nome": user.get_full_name() or user.email,
                 "role": user.role, "is_admin": user.is_admin},
    }


def _register_failure(user):
    if user is None:
        return
    user.failed_logins += 1
    if user.failed_logins >= settings.LOGIN_MAX_ATTEMPTS:
        user.locked_until = timezone.now() + settings.LOGIN_LOCKOUT
        user.failed_logins = 0
    user.save(update_fields=["failed_logins", "locked_until"])


@api_view(["GET"])
@permission_classes([AllowAny])
@ensure_csrf_cookie
def me(request):
    return Response(user_payload(request))


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField()
    otp = serializers.CharField(required=False, allow_blank=True)


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([LoginThrottle])
def login_view(request):
    data = LoginSerializer(data=request.data)
    data.is_valid(raise_exception=True)
    email = data.validated_data["email"].lower()
    existing = User.objects.filter(email__iexact=email).first()
    if existing and existing.is_locked:
        return Response({"detail": "Conta bloqueada temporariamente por excesso de tentativas. Tente em 15 minutos."},
                        status=status.HTTP_423_LOCKED)

    user = authenticate(request, username=email, password=data.validated_data["password"])
    if user is None:
        _register_failure(existing)
        return Response({"detail": "E-mail ou senha inválidos."}, status=status.HTTP_400_BAD_REQUEST)

    device = TOTPDevice.objects.filter(user=user, confirmed=True).first()
    if settings.REQUIRE_2FA and device:
        otp = (data.validated_data.get("otp") or "").replace(" ", "")
        if not otp:
            return Response({"otp_required": True}, status=status.HTTP_200_OK)
        if not device.verify_token(otp):
            _register_failure(user)
            return Response({"detail": "Código de verificação inválido.", "otp_required": True},
                            status=status.HTTP_400_BAD_REQUEST)
        login(request, user)
        otp_login(request, device)
    else:
        login(request, user)

    user.failed_logins = 0
    user.save(update_fields=["failed_logins"])
    log_activity(user, "login", user)
    return Response(user_payload(request))


@api_view(["POST"])
@permission_classes([AllowAny])
def logout_view(request):
    logout(request)
    return Response({"authenticated": False})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def totp_setup(request):
    """Gera (ou regenera) o segredo TOTP ainda não confirmado e devolve o QR code."""
    if TOTPDevice.objects.filter(user=request.user, confirmed=True).exists():
        return Response({"detail": "2FA já configurado."}, status=status.HTTP_400_BAD_REQUEST)
    TOTPDevice.objects.filter(user=request.user, confirmed=False).delete()
    device = TOTPDevice.objects.create(user=request.user, name="Aplicativo autenticador", confirmed=False)
    uri = device.config_url  # inclui OTP_TOTP_ISSUER no rótulo
    img = qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage, box_size=8)
    buf = io.BytesIO()
    img.save(buf)
    return Response({"otpauth_uri": uri, "qr_svg": buf.getvalue().decode()})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def totp_confirm(request):
    device = TOTPDevice.objects.filter(user=request.user, confirmed=False).order_by("-id").first()
    otp = str(request.data.get("otp", "")).replace(" ", "")
    if not device or not device.verify_token(otp):
        return Response({"detail": "Código inválido. Confira o horário do celular e tente de novo."},
                        status=status.HTTP_400_BAD_REQUEST)
    device.confirmed = True
    device.save()
    otp_login(request, device)
    log_activity(request.user, "2fa_configurado", request.user)
    return Response(user_payload(request))
