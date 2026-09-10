import logging
import threading

from django.contrib.staticfiles.management.commands.runserver import (
    Command as StaticFilesRunserverCommand,
)
from django.core.management.base import CommandError

from bale_bot.client import BaleBotClient
from bale_bot.handlers import handle_update
from bale_bot.polling import run_long_polling


logger = logging.getLogger(__name__)


class Command(StaticFilesRunserverCommand):
    help = 'Starts Django development server and Bale long polling together.'

    def inner_run(self, *args, **options):
        self._start_bale_polling()
        return super().inner_run(*args, **options)

    def _start_bale_polling(self):
        if getattr(self, '_bale_polling_thread', None):
            return

        try:
            client = BaleBotClient.from_env()
        except RuntimeError as error:
            raise CommandError(str(error)) from error

        thread = threading.Thread(
            target=self._run_bale_polling,
            args=(client,),
            name='bale-bot-polling',
            daemon=True,
        )
        thread.start()
        self._bale_polling_thread = thread
        self.stdout.write(self.style.SUCCESS('Bale bot polling started.'))

    @staticmethod
    def _run_bale_polling(client):
        try:
            run_long_polling(client=client, update_handler=handle_update)
        except Exception:
            logger.exception('Bale polling thread stopped unexpectedly.')
