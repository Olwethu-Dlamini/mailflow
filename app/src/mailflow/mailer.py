"""Talking to mail servers directly: checking the IMAP or SMTP sign-in an admin entered, and sending a
reply over SMTP in the same conversation (In-Reply-To and References name the email answered, so the
customer's mail app threads it).

These calls block (imaplib, smtplib); the web app runs them in a worker thread. Connections are
always encrypted: IMAP over TLS (port 993), SMTP over TLS (465) or upgraded with STARTTLS (587).
"""

import imaplib
import re
import smtplib
import ssl
from dataclasses import asdict, dataclass
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid, parseaddr

TIMEOUT = 20
SECURITY = ("ssl", "starttls")
# A real Message-ID; emails without one were given "<date|subject>" by the collector, which answers nothing.
MESSAGE_ID = re.compile(r"<[^<>\s]+@[^<>\s]+>")
ADDRESS = re.compile(r"[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+")

# The classes used to connect; tests put stand-ins here.
IMAP = imaplib.IMAP4_SSL
SMTP_SSL = smtplib.SMTP_SSL
SMTP = smtplib.SMTP


class MailError(Exception):
    """A mail server refused, or could not be reached; the message is for people."""


@dataclass(frozen=True)
class Smtp:
    """How replies from one mailbox are sent. The password is kept apart (sealed, see vault.py)."""

    host: str
    port: int
    security: str  # one of SECURITY
    user: str
    from_address: str
    from_name: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def _one_line(text: str) -> str:
    return " ".join(str(text).split())


def _why(error: Exception) -> str:
    text = error.args[-1] if error.args else error
    if isinstance(text, bytes):
        text = text.decode(errors="replace")
    return _one_line(text)[:200] or error.__class__.__name__


def check_imap(host: str, port: int, user: str, password: str) -> None:
    """Sign in and open INBOX read-only; MailError says what went wrong."""
    try:
        with IMAP(host, port, ssl_context=ssl.create_default_context(), timeout=TIMEOUT) as imap:
            imap.login(user, password)
            status, _ = imap.select("INBOX", readonly=True)
            if status != "OK":
                raise MailError("Signed in, but the mailbox has no INBOX folder.")
    except imaplib.IMAP4.error as error:
        raise MailError(f"The mail server refused the sign-in: {_why(error)}") from None
    except ssl.SSLError as error:
        raise MailError(f"No secure connection to {host}:{port} ({_why(error)}). IMAP needs TLS, usually port 993.") from None
    except OSError as error:
        raise MailError(f"Could not reach {host}:{port} ({_why(error)}).") from None


def _open_smtp(smtp: Smtp, password: str) -> smtplib.SMTP:
    if smtp.security not in SECURITY:
        raise MailError("Choose SSL (usually port 465) or STARTTLS (usually port 587).")
    context = ssl.create_default_context()
    if smtp.security == "ssl":
        server = SMTP_SSL(smtp.host, smtp.port, timeout=TIMEOUT, context=context)
    else:
        server = SMTP(smtp.host, smtp.port, timeout=TIMEOUT)
        try:
            server.starttls(context=context)
        except BaseException:
            server.close()
            raise
    try:
        server.login(smtp.user, password)
    except BaseException:
        server.close()
        raise
    return server


def _smtp_errors(smtp: Smtp, action):
    try:
        return action()
    except smtplib.SMTPAuthenticationError as error:
        raise MailError(f"The SMTP server refused the sign-in: {_why(error)}") from None
    except smtplib.SMTPRecipientsRefused:
        raise MailError("The SMTP server refused the address this reply goes to.") from None
    except smtplib.SMTPNotSupportedError:
        raise MailError(f"{smtp.host} does not offer STARTTLS on port {smtp.port}: try SSL on port 465.") from None
    except smtplib.SMTPException as error:
        raise MailError(f"The SMTP server refused: {_why(error)}") from None
    except ssl.SSLError as error:
        raise MailError(f"No secure connection to {smtp.host}:{smtp.port} ({_why(error)}).") from None
    except OSError as error:
        raise MailError(f"Could not reach {smtp.host}:{smtp.port} ({_why(error)}).") from None


def check_smtp(smtp: Smtp, password: str) -> None:
    """Sign in and leave; MailError says what went wrong."""

    def sign_in():
        _open_smtp(smtp, password).quit()

    _smtp_errors(smtp, sign_in)


def reply_message(smtp: Smtp, to_name: str, to_address: str, subject: str, message_id: str, text: str) -> EmailMessage:
    """The reply as it will leave: from the mailbox, to the sender, "Re:" the subject, in the thread."""
    to_address = to_address.strip()
    if not ADDRESS.fullmatch(to_address):
        raise MailError("This email has no sender address to answer.")
    subject = _one_line(subject) or "(no subject)"
    message = EmailMessage()
    message["From"] = formataddr((_one_line(smtp.from_name), smtp.from_address))
    message["To"] = formataddr((_one_line(to_name), to_address))
    message["Subject"] = subject if subject.lower().startswith("re:") else f"Re: {subject}"
    message["Date"] = formatdate(usegmt=True)
    message["Message-ID"] = make_msgid(domain=smtp.from_address.rpartition("@")[2] or None)
    message_id = message_id.strip()
    if MESSAGE_ID.fullmatch(message_id):
        message["In-Reply-To"] = message_id
        message["References"] = message_id
    message.set_content(text)
    return message


def send(smtp: Smtp, password: str, message: EmailMessage) -> None:
    def deliver():
        server = _open_smtp(smtp, password)
        try:
            server.send_message(message, from_addr=parseaddr(message["From"])[1])
        finally:
            server.quit()

    _smtp_errors(smtp, deliver)
