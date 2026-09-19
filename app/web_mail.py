"""Bounded SMTP delivery; callers expose only a generic failure code."""
from email.message import EmailMessage
import smtplib
import ssl

from app.web_config import WebSettings


class SmtpMailer:
    def __init__(self, settings: WebSettings):
        self.settings = settings

    def send(self, recipient: str, purpose: str, token: str) -> None:
        settings = self.settings
        message = EmailMessage()
        message["From"] = settings.sender
        message["To"] = recipient
        message["Subject"] = "PsychologyAtlas — подтверждение почты" if purpose == "register" else "PsychologyAtlas — восстановление доступа"
        # A fragment never reaches HTTP access logs or the Referer header.
        action = "verify" if purpose == "register" else "recover"
        message.set_content(
            f"Откройте ссылку и задайте пароль:\n{settings.origin}/#{action}={token}\n\n"
            "Если вы не запрашивали это действие, проигнорируйте письмо.\n"
            "Никому не пересылайте ссылку."
        )
        context = ssl.create_default_context()
        if settings.smtp_port == 465:
            client = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=10, context=context)
        else:
            client = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10)
        with client:
            if settings.smtp_port == 587:
                client.ehlo()
                client.starttls(context=context)
                client.ehlo()
            client.login(settings.smtp_username, settings.smtp_password)
            client.send_message(message)
