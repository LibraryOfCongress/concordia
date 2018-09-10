"""
Sendmail email backend class.
Credits: https://djangosnippets.org/snippets/1864/
"""
from django.core.mail.backends.base import BaseEmailBackend
from subprocess import Popen, PIPE


class SendmailEmailBackend(BaseEmailBackend):
    """
    A wrapper that calls the sendmail program.
    """
    def send_messages(self, email_messages):
        """
        Sends one or more EmailMessage objects and returns the number of email
        messages sent.
        """
        if not email_messages:
            return
        num_sent = 0
        for message in email_messages:
            if self._send(message):
                num_sent += 1
        return num_sent

    def _send(self, email_message):
        """A helper method that does the actual sending."""
        recipients = email_message.recipients()
        if not recipients:
            return False
        try:
            # -t: Read message for recipients
            ps = Popen(['/usr/sbin/sendmail'] + recipients, stdin=PIPE,
                       stderr=PIPE)
            ps.stdin.write(email_message.message().as_bytes())
            (stdout, stderr) = ps.communicate()
        except Exception as e:
            if not self.fail_silently:
                raise e
            return False
        if ps.returncode:
            if not self.fail_silently:
                error = stderr if stderr else stdout
                raise Exception('send_messages failed: %s' % error)
            return False
        return True
