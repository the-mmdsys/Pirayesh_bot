import json
import os
from unittest.mock import Mock, patch

from django.test import TestCase
from django.urls import reverse


class HealthCheckTests(TestCase):
    def test_health_check_returns_ok_without_sensitive_data(self):
        response = self.client.get(reverse('health_check'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok'})


class BaleWebhookTests(TestCase):
    def test_webhook_rejects_get_requests(self):
        response = self.client.get(reverse('bale_webhook'))

        self.assertEqual(response.status_code, 405)

    def test_webhook_rejects_invalid_json(self):
        response = self.client.post(
            reverse('bale_webhook'),
            data='not-json',
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {'status': 'invalid_json'})

    def test_webhook_rejects_invalid_secret_when_secret_is_configured(self):
        with patch.dict(os.environ, {'BALE_WEBHOOK_SECRET': 'expected'}, clear=False):
            response = self.client.post(
                reverse('bale_webhook'),
                data=json.dumps({'update_id': 1}),
                content_type='application/json',
                HTTP_X_BALE_WEBHOOK_SECRET='wrong',
            )

        self.assertEqual(response.status_code, 403)

    @patch('bale_bot.webhook_views.handle_update')
    @patch('bale_bot.webhook_views.BaleBotClient.from_env')
    def test_webhook_passes_update_to_existing_handler(self, from_env, handle_update):
        client = Mock()
        from_env.return_value = client
        update = {'update_id': 1, 'message': {'chat': {'id': 10}, 'text': '/start'}}

        with patch.dict(os.environ, {'BALE_WEBHOOK_SECRET': 'expected'}, clear=False):
            response = self.client.post(
                reverse('bale_webhook'),
                data=json.dumps(update),
                content_type='application/json',
                HTTP_X_BALE_WEBHOOK_SECRET='expected',
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok'})
        handle_update.assert_called_once_with(update, client)
