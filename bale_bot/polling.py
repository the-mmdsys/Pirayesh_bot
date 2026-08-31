import logging
import time

from bale_bot.client import BaleAPIError


logger = logging.getLogger(__name__)


def run_long_polling(
    client,
    update_handler,
    start_offset=0,
    poll_timeout=20,
    request_timeout=30,
    sleep_on_error=2,
):
    last_update_id = start_offset

    while True:
        try:
            updates = client.get_updates(
                offset=last_update_id + 1,
                timeout=poll_timeout,
                request_timeout=request_timeout,
            )

            for update in updates:
                last_update_id = update['update_id']
                update_handler(update, client)

        except BaleAPIError as error:
            logger.error('Bale API error: %s', error)
            time.sleep(sleep_on_error)
        except KeyboardInterrupt:
            print('Bot stopped.')
            break
        except Exception:
            logger.exception('Unexpected bot error in long polling.')
            time.sleep(sleep_on_error)
