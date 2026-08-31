import unittest

from bale_bot.client import BaleAPIError, BaleBotClient


class FakeResponse:
    def __init__(self, payload, status_error=None):
        self.payload = payload
        self.status_error = status_error

    def raise_for_status(self):
        if self.status_error:
            raise self.status_error

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self):
        self.calls = []
        self.next_response = FakeResponse({'ok': True, 'result': []})

    def get(self, url, **kwargs):
        self.calls.append(('get', url, kwargs))
        return self.next_response

    def post(self, url, **kwargs):
        self.calls.append(('post', url, kwargs))
        return self.next_response


class BaleBotClientTests(unittest.TestCase):
    def setUp(self):
        self.session = FakeSession()
        self.client = BaleBotClient(token='test-token', session=self.session)

    def test_get_updates_sends_offset_and_timeout(self):
        self.client.get_updates(offset=10, timeout=20, request_timeout=30)

        method, url, kwargs = self.session.calls[0]
        self.assertEqual(method, 'get')
        self.assertTrue(url.endswith('/getUpdates'))
        self.assertEqual(kwargs['params'], {'timeout': 20, 'offset': 10})
        self.assertEqual(kwargs['timeout'], 30)

    def test_send_message_posts_text_payload(self):
        self.client.send_message(chat_id=123, text='hello')

        method, url, kwargs = self.session.calls[0]
        self.assertEqual(method, 'post')
        self.assertTrue(url.endswith('/sendMessage'))
        self.assertEqual(kwargs['json']['chat_id'], 123)
        self.assertEqual(kwargs['json']['text'], 'hello')

    def test_send_reply_keyboard_adds_reply_markup(self):
        keyboard = [[{'text': 'Reserve'}]]

        self.client.send_reply_keyboard(chat_id=123, text='choose', keyboard=keyboard)

        payload = self.session.calls[0][2]['json']
        self.assertEqual(payload['reply_markup']['keyboard'], keyboard)
        self.assertTrue(payload['reply_markup']['resize_keyboard'])

    def test_api_error_is_raised_without_leaking_token_in_message(self):
        self.session.next_response = FakeResponse({'ok': False, 'description': 'bad request'})

        with self.assertRaises(BaleAPIError) as context:
            self.client.get_me()

        self.assertNotIn('test-token', str(context.exception))
        self.assertIn('getMe', str(context.exception))


if __name__ == '__main__':
    unittest.main()
