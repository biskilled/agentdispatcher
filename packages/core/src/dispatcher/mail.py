"""Email transport with no logging of bearer links or provider credentials."""

import smtplib
from email.message import EmailMessage

from dispatcher.settings import Settings


class Mailer:
    """Send login links through the deployment's SMTP provider."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def send_login(self, email: str, token: str) -> None:
        """Put the token in a fragment so reverse-proxy access logs do not capture it."""
        settings = self.settings
        if not settings.smtp_host or not settings.smtp_sender:
            raise RuntimeError("Email sign-in requires SMTP configuration")
        message = EmailMessage()
        message["From"] = settings.smtp_sender
        message["To"] = email
        message["Subject"] = "Sign in to AgentDispatcher"
        message.set_content(
            "Open this link and select Continue to sign in.\n\n"
            + settings.public_url.rstrip("/")
            + "/#signin="
            + token
            + "\n\nIf you did not request this link, ignore this email."
        )
        with smtplib.SMTP(
            settings.smtp_host, settings.smtp_port, timeout=settings.http_timeout
        ) as client:
            if settings.smtp_starttls:
                client.starttls()
            if settings.smtp_user:
                client.login(settings.smtp_user, settings.smtp_password.get_secret_value())
            client.send_message(message)
