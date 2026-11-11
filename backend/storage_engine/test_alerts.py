from datetime import timedelta
from unittest import mock

from django.utils import timezone

from drive.models import StorageSettings
from storage_engine import alerts, health
from storage_engine.fakes import REAL_RESOLVE, StorageTestCase

WEBHOOK = 'https://ntfy.example.com/my-topic'
# the real transport/resolver, captured before StorageTestCase patches them
ORIGINAL_POST = alerts._post


class AlertStateMachineTests(StorageTestCase):
    def setUp(self):
        super().setUp()
        row = StorageSettings.get_solo()
        row.alert_webhook_url = WEBHOOK
        row.alert_min_interval_minutes = 30
        row.save()

    def test_first_failure_alerts_immediately(self):
        self.assertTrue(alerts.report_failure('telegram_session_expired'))
        self.assertEqual(len(self.sent), 1)
        row = StorageSettings.objects.get(pk=1)
        self.assertEqual((row.alert_state, row.last_check_ok, row.last_check_reason),
                         ('down', False, 'telegram_session_expired'))

    def test_repeats_are_suppressed_inside_the_interval_then_sent_after_it(self):
        alerts.report_failure('telegram_session_expired')
        self.assertFalse(alerts.report_failure('telegram_session_expired'))
        self.assertEqual(len(self.sent), 1)

        StorageSettings.objects.filter(pk=1).update(last_alert_at=timezone.now() - timedelta(minutes=31))
        self.assertTrue(alerts.report_failure('telegram_session_expired'))
        self.assertEqual(len(self.sent), 2)

    def test_recovery_is_sent_once(self):
        alerts.report_failure('telegram_unreachable')
        self.assertTrue(alerts.report_ok())
        self.assertFalse(alerts.report_ok())
        self.assertEqual(len(self.sent), 2)
        self.assertIn('recovered', self.sent[1][1]['headers']['Title'])
        self.assertEqual(StorageSettings.objects.get(pk=1).alert_state, 'ok')

    def test_ok_while_ok_sends_nothing(self):
        self.assertFalse(alerts.report_ok())
        self.assertEqual(self.sent, [])

    def test_health_helpers_drive_the_state_machine(self):
        health.record_failure('channel_unreachable')
        health.record_success()
        self.assertEqual(len(self.sent), 2)

    def test_session_expired_message_says_what_to_do_and_links_settings(self):
        alerts.remember_host('https://drive.example.com')
        self.addCleanup(alerts.remember_host, '')
        alerts.report_failure('telegram_session_expired')
        body = self.sent[0][1]['data'].decode()
        self.assertIn('Reconnect Telegram', body)
        self.assertIn('https://drive.example.com/settings/storage', body)

    def test_sending_never_raises(self):
        with mock.patch.object(alerts, '_post', side_effect=RuntimeError('network down')):
            with self.assertLogs('storage_engine.alerts', level='WARNING'):
                self.assertTrue(alerts.report_failure('telegram_unreachable'))

    def test_failure_logs_never_contain_the_webhook_url(self):
        with mock.patch.object(alerts, '_post', side_effect=RuntimeError(WEBHOOK)):
            with self.assertLogs('storage_engine.alerts', level='WARNING') as logs:
                alerts.report_failure('telegram_unreachable')
        self.assertNotIn('my-topic', '\n'.join(r.getMessage() for r in logs.records))


class AlertFormatTests(StorageTestCase):
    def deliver(self, fmt, state='down'):
        row = StorageSettings.get_solo()
        row.alert_format, row.alert_webhook_url = fmt, WEBHOOK
        row.save()
        alerts.deliver(alerts.channels_from_row(row), 'Title', 'Message', reason='telegram_unreachable', state=state)
        return self.sent[-1]

    def test_ntfy_plain_text_with_title_and_high_priority(self):
        url, kwargs = self.deliver('ntfy')
        self.assertEqual(url, WEBHOOK)
        self.assertEqual(kwargs['data'], b'Message')
        self.assertEqual(kwargs['headers'], {'Title': 'Title', 'Priority': 'high'})

    def test_ntfy_recovery_is_not_high_priority(self):
        _, kwargs = self.deliver('ntfy', state='ok')
        self.assertEqual(kwargs['headers']['Priority'], 'default')

    def test_discord_json(self):
        _, kwargs = self.deliver('discord')
        self.assertEqual(kwargs['json'], {'content': 'Title\nMessage'})

    def test_slack_json(self):
        _, kwargs = self.deliver('slack')
        self.assertEqual(kwargs['json'], {'text': 'Title\nMessage'})

    def test_generic_json(self):
        _, kwargs = self.deliver('generic')
        body = kwargs['json']
        self.assertEqual({k: body[k] for k in ('title', 'message', 'reason', 'state')},
                         {'title': 'Title', 'message': 'Message', 'reason': 'telegram_unreachable', 'state': 'down'})
        self.assertIn('time', body)

    def test_telegram_dm_uses_bot_token_and_never_logs_it(self):
        row = StorageSettings.get_solo()
        row.alert_telegram_chat_id = '42'
        row.save()
        with mock.patch.object(alerts.config, 'TELEGRAM_BOT_TOKEN', 'BOT:SECRET'):
            results = alerts.deliver(alerts.channels_from_row(row), 'T', 'M')
        self.assertEqual(results, {'telegram': 'ok'})
        url, kwargs = self.sent[0]
        self.assertEqual(url, 'https://api.telegram.org/botBOT:SECRET/sendMessage')
        self.assertEqual(kwargs['json'], {'chat_id': '42', 'text': 'T\nM'})

    def test_telegram_dm_without_bot_token_reports_error(self):
        row = StorageSettings.get_solo()
        row.alert_telegram_chat_id = '42'
        row.save()
        with mock.patch.object(alerts.config, 'TELEGRAM_BOT_TOKEN', ''):
            results = alerts.deliver(alerts.channels_from_row(row), 'T', 'M')
        self.assertTrue(results['telegram'].startswith('error'))

    def test_non_2xx_is_an_error_result(self):
        with mock.patch.object(alerts, '_post', return_value=mock.Mock(status_code=404)):
            results = alerts.deliver({'format': 'ntfy', 'webhook_url': WEBHOOK, 'telegram_chat_id': ''}, 'T', 'M')
        self.assertEqual(results, {'webhook': 'error: HTTP 404'})


class SsrfGuardTests(StorageTestCase):
    def test_public_https_is_accepted(self):
        alerts.validate_webhook_url(WEBHOOK)

    def test_rejects_literal_private_and_loopback_addresses(self):
        for url in ('https://127.0.0.1/x', 'https://10.0.0.1/x', 'https://192.168.1.5/x',
                    'https://169.254.169.254/latest/meta-data', 'https://[::1]/x', 'https://[::ffff:10.0.0.1]/x'):
            with self.subTest(url=url), mock.patch.object(alerts, '_resolve', side_effect=REAL_RESOLVE):
                with self.assertRaises(ValueError):
                    alerts.validate_webhook_url(url)

    def test_rejects_non_https(self):
        with self.assertRaises(ValueError):
            alerts.validate_webhook_url('http://ntfy.example.com/topic')

    def test_rejects_hostname_resolving_to_private_address(self):
        with mock.patch.object(alerts, '_resolve', return_value=['10.1.2.3']):
            with self.assertRaises(ValueError):
                alerts.validate_webhook_url('https://innocent.example.com/x')

    def test_rejects_when_any_resolved_address_is_private(self):
        with mock.patch.object(alerts, '_resolve', return_value=['93.184.216.34', '127.0.0.1']):
            with self.assertRaises(ValueError):
                alerts.validate_webhook_url('https://mixed.example.com/x')

    def test_send_time_recheck_blocks_a_url_that_later_resolves_privately(self):
        channels = {'format': 'ntfy', 'webhook_url': WEBHOOK, 'telegram_chat_id': ''}
        with mock.patch.object(alerts, '_resolve', return_value=['10.0.0.9']):
            results = alerts.deliver(channels, 'T', 'M')
        self.assertTrue(results['webhook'].startswith('error'))
        self.assertEqual(self.sent, [])

    def test_post_refuses_redirects_and_times_out_in_5_seconds(self):
        with mock.patch.object(alerts.requests, 'post') as post:
            ORIGINAL_POST('https://ntfy.example.com/t', data=b'x')
        _, kwargs = post.call_args
        self.assertIs(kwargs['allow_redirects'], False)
        self.assertEqual(kwargs['timeout'], 5)
