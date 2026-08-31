import os

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from bale_bot.client import BaleBotClient
from bale_bot.handlers import handle_update
from bale_bot.polling import run_long_polling


def main():
    client = BaleBotClient.from_env()
    print('Bot started.')
    print('Waiting for Bale messages...')
    run_long_polling(client=client, update_handler=handle_update)


if __name__ == '__main__':
    main()
