from bale_bot.client import BaleBotClient
from bale_bot.polling import run_long_polling


def print_update(update, client):
    message = update.get('message')
    callback_query = update.get('callback_query')

    print('--------------------')
    print('update_id:', update.get('update_id'))

    if message:
        chat = message.get('chat') or {}
        print('event: message')
        print('chat_id:', chat.get('id'))
        print('text:', message.get('text'))
        return

    if callback_query:
        print('event: callback_query')
        print('data:', callback_query.get('data'))
        return

    print('event: unsupported')


def main():
    client = BaleBotClient.from_env()
    print('Listening for Bale updates...')
    run_long_polling(client=client, update_handler=print_update)


if __name__ == '__main__':
    main()
