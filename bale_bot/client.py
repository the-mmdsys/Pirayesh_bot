import os
from pathlib import Path

import requests
from dotenv import load_dotenv


class BaleAPIError(RuntimeError):
    pass


class BaleBotClient:
    api_base_url = 'https://tapi.bale.ai'

    def __init__(self, token, session=None):
        if not token:
            raise RuntimeError('BALE_BOT_TOKEN is missing in .env')
        self.token = token
        self.session = session or requests.Session()
        self.base_url = f'{self.api_base_url}/bot{self.token}'

    @classmethod
    def from_env(cls):
        env_path = Path(__file__).resolve().parent.parent / '.env'
        load_dotenv(env_path)
        return cls(token=os.getenv('BALE_BOT_TOKEN'))

    def get_me(self):
        return self._request('get', 'getMe')

    def get_updates(self, offset=None, timeout=20, request_timeout=30):
        params = {'timeout': timeout}
        if offset is not None:
            params['offset'] = offset
        return self._request('get', 'getUpdates', params=params, timeout=request_timeout)

    def send_message(self, chat_id, text, reply_markup=None):
        payload = {
            'chat_id': chat_id,
            'text': text,
        }
        if reply_markup:
            payload['reply_markup'] = reply_markup
        return self._request('post', 'sendMessage', json=payload)

    def send_reply_keyboard(self, chat_id, text, keyboard, resize_keyboard=True, one_time_keyboard=False):
        reply_markup = {
            'keyboard': keyboard,
            'resize_keyboard': resize_keyboard,
            'one_time_keyboard': one_time_keyboard,
        }
        return self.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)

    def send_inline_keyboard(self, chat_id, text, inline_keyboard):
        reply_markup = {
            'inline_keyboard': inline_keyboard,
        }
        return self.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)

    def _request(self, method, endpoint, **kwargs):
        url = f'{self.base_url}/{endpoint}'
        try:
            response = getattr(self.session, method)(url, **kwargs)
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as error:
            raise BaleAPIError(f'Bale API request failed for {endpoint}') from None
        except ValueError as error:
            raise BaleAPIError(f'Bale API returned invalid JSON for {endpoint}') from None

        if not data.get('ok'):
            description = data.get('description') or 'Unknown Bale API error'
            raise BaleAPIError(f'Bale API error in {endpoint}: {description}')

        return data.get('result')
