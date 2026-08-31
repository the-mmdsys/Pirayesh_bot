from bale_bot.client import BaleBotClient


def main():
    client = BaleBotClient.from_env()
    print(client.get_me())


if __name__ == '__main__':
    main()
