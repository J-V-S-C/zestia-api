import logging
import smtplib
import ssl
from email.message import EmailMessage

from app.config import SmtpSettings

logger = logging.getLogger(__name__)


class SmtpRecoveryDelivery:
    def __init__(self, settings: SmtpSettings, token_minutes: int) -> None:
        self.settings = settings
        self.token_minutes = token_minutes

    def __call__(self, recipient: str, token: str) -> None:
        try:
            message = EmailMessage()
            message["Subject"] = "Zestia — recuperação de conta"
            message["From"] = str(self.settings.smtp_username)
            message["To"] = recipient
            message.set_content(
                "Seu código de recuperação da conta Zestia:\n\n"
                f"{token}\n\n"
                f"Este código expira em {self.token_minutes} minutos e só pode ser usado uma vez.\n"
                "Se você não solicitou a recuperação, ignore esta mensagem.\n"
            )
            with smtplib.SMTP(
                self.settings.smtp_host,
                self.settings.smtp_port,
                timeout=self.settings.smtp_timeout_seconds,
            ) as connection:
                connection.ehlo()
                connection.starttls(context=ssl.create_default_context())
                connection.ehlo()
                connection.login(
                    str(self.settings.smtp_username), self.settings.smtp_password.get_secret_value()
                )
                refused = connection.send_message(message)
                if refused:
                    logger.error("Recovery email delivery failed.")
        except (smtplib.SMTPException, OSError, ValueError):
            # Provider errors may contain addresses, passwords or message content.
            # Keep the public response generic and never log those exception strings.
            logger.error("Recovery email delivery failed.")
