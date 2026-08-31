import logging
import os


SENSITIVE_ENV_NAMES = {
    'BALE_BOT_TOKEN',
    'DB_PASSWORD',
    'DJANGO_SECRET_KEY',
}


class SensitiveDataFilter(logging.Filter):
    def filter(self, record):
        message = record.getMessage()
        for value in sensitive_values():
            message = message.replace(value, '[FILTERED]')
        record.msg = message
        record.args = ()
        return True


def sensitive_values():
    for name in SENSITIVE_ENV_NAMES:
        value = os.getenv(name)
        if value:
            yield value
