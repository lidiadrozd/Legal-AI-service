from __future__ import annotations

import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib

from app.core.config import settings

logger = logging.getLogger(__name__)


async def send_reset_password_email(to_email: str, reset_url: str) -> None:
    message = MIMEMultipart("alternative")
    message["Subject"] = "Сброс пароля — Legal AI"
    message["From"] = settings.SMTP_FROM
    message["To"] = to_email

    text = (
        f"Вы запросили сброс пароля для вашего аккаунта в Legal AI.\n\n"
        f"Перейдите по ссылке для создания нового пароля:\n{reset_url}\n\n"
        f"Ссылка действительна 1 час.\n\n"
        f"Если вы не запрашивали сброс пароля — просто проигнорируйте это письмо."
    )

    html = f"""
<!DOCTYPE html>
<html>
<body style="font-family:sans-serif;color:#1a1a1a;max-width:480px;margin:0 auto;padding:24px;">
  <h2 style="font-size:20px;margin-bottom:8px;">Сброс пароля</h2>
  <p style="color:#555;margin-bottom:24px;">
    Вы запросили сброс пароля для вашего аккаунта в <strong>Legal AI</strong>.
  </p>
  <a href="{reset_url}"
     style="display:inline-block;padding:12px 24px;background:#2563eb;color:#fff;
            border-radius:8px;text-decoration:none;font-weight:600;margin-bottom:24px;">
    Сбросить пароль
  </a>
  <p style="color:#888;font-size:13px;">
    Ссылка действительна <strong>1 час</strong>.<br>
    Если вы не запрашивали сброс пароля — просто проигнорируйте это письмо.
  </p>
</body>
</html>
"""

    message.attach(MIMEText(text, "plain", "utf-8"))
    message.attach(MIMEText(html, "html", "utf-8"))

    await aiosmtplib.send(
        message,
        hostname=settings.SMTP_HOST,
        port=settings.SMTP_PORT,
        username=settings.SMTP_USER,
        password=settings.SMTP_PASSWORD,
        start_tls=True,
    )
    logger.info("Reset password email sent to %s", to_email)
