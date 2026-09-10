from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from bale_bot.management.commands.runserver import Command


class RunserverCommandTests(SimpleTestCase):
    @patch('bale_bot.management.commands.runserver.threading.Thread')
    @patch('bale_bot.management.commands.runserver.BaleBotClient.from_env')
    def test_bale_polling_starts_once_in_a_daemon_thread(self, from_env, thread_class):
        client = Mock()
        thread = Mock()
        from_env.return_value = client
        thread_class.return_value = thread
        command = Command()

        command._start_bale_polling()
        command._start_bale_polling()

        from_env.assert_called_once_with()
        thread_class.assert_called_once_with(
            target=command._run_bale_polling,
            args=(client,),
            name='bale-bot-polling',
            daemon=True,
        )
        thread.start.assert_called_once_with()
