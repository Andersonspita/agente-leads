from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import User


class Command(BaseCommand):
    help = "Cria uma conta interna (admin ou analista). O 2FA é configurado no primeiro login."

    def add_arguments(self, parser):
        parser.add_argument("email")
        parser.add_argument("--nome", default="")
        parser.add_argument("--role", choices=["admin", "analista"], default="analista")
        parser.add_argument("--password", required=True)

    def handle(self, *args, **opts):
        if User.objects.filter(email__iexact=opts["email"]).exists():
            raise CommandError("Já existe uma conta com este e-mail.")
        first, _, last = opts["nome"].partition(" ")
        is_admin = opts["role"] == "admin"
        User.objects.create_user(
            email=opts["email"], password=opts["password"], first_name=first, last_name=last,
            role=opts["role"], is_staff=is_admin, is_superuser=is_admin,
        )
        self.stdout.write(self.style.SUCCESS(f"Conta {opts['email']} ({opts['role']}) criada."))
