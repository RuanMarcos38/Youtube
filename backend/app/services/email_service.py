import smtplib
from email.message import EmailMessage

from ..config import settings


def smtp_configured() -> bool:
    return bool(settings.smtp_host.strip() and settings.smtp_from.strip())


def send_access_credentials(email: str, name: str, temporary_password: str) -> bool:
    if not smtp_configured():
        return False

    message = EmailMessage()
    message["Subject"] = "Seu acesso ao ShortsFlow AI foi liberado"
    message["From"] = settings.smtp_from
    message["To"] = email
    message.set_content(
        f"Olá, {name or 'cliente'}!\n\n"
        "Seu pagamento foi confirmado e o acesso ao ShortsFlow AI está liberado.\n\n"
        f"Login: {email}\n"
        f"Senha inicial: {temporary_password}\n\n"
        f"Acesse: {settings.frontend_url}\n\n"
        "Por segurança, altere a senha após o primeiro acesso."
    )

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as server:
            if settings.smtp_use_tls:
                server.starttls()
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(message)
        return True
    except Exception:
        return False
