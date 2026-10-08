import functools
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import main
from src import analyze_visitor as visitor


def record(ip, time_text, path='/', status=200, user='游客'):
    return {'time': time_text, 'ip': ip, 'user': user, 'path': path,
            'method': 'GET', 'status': status}


# 用相对日期构造记录，保证 30 天趋势断言不会随日期推移失效。
def day(offset):
    return (datetime.now() - timedelta(days=offset)).strftime('%Y-%m-%d')


RECORDS = [
    record('1.1.1.1', f'{day(4)} 10:00:00'),
    record('1.1.1.1', f'{day(4)} 11:00:00'),
    record('1.1.1.1', f'{day(3)} 12:00:00', path='/pages/home/', user='hyper'),
    record('2.2.2.2', f'{day(3)} 13:00:00', path='/pages/home/'),
    record('3.3.3.3', f'{day(3)} 14:00:00', path='/wp-login.php', status=404),
    record('3.3.3.3', f'{day(3)} 15:00:00', path='/wp-login.php', status=404),
    record('4.4.4.4', f'{day(2)} 08:00:00', path='/'),
    record('4.4.4.4', f'{day(2)} 09:00:00', path='/'),
    record('4.4.4.4', f'{day(2)} 10:00:00', path='/static/css/home.css'),
    record('4.4.4.4', f'{day(2)} 11:00:00', path='/'),
    record('4.4.4.4', f'{day(2)} 12:00:00', path='/'),
    record('5.5.5.5', f'{day(2)} 13:00:00', path='/'),
    record('127.0.0.1', f'{day(0)} 09:00:00', path='/', user='hyper'),
    record('127.0.0.1', f'{day(0)} 09:30:00', path='/visit-count'),
]

REGION_MAP = {
    '1.1.1.1': '🇨🇳 浙江省 · 杭州市',
    '2.2.2.2': '🇨🇳 浙江省 · 杭州市',
    '3.3.3.3': '🇨🇳 广东省 · 深圳市',
    '4.4.4.4': '🌍 United States',
    '5.5.5.5': '🌍 Japan',
}


def build_payload():
    with patch.object(visitor, 'region_label', side_effect=lambda ip: REGION_MAP[ip]):
        return visitor.build_stats_payload(RECORDS)


class StatsPayloadTests(unittest.TestCase):
    def test_domestic_first_then_overseas_sorted_by_visits(self):
        payload = build_payload()

        self.assertEqual([region['name'] for region in payload['domestic']],
                         ['浙江省 · 杭州市', '广东省 · 深圳市'])
        self.assertEqual([region['visits'] for region in payload['domestic']], [4, 2])
        self.assertEqual([region['name'] for region in payload['overseas']],
                         ['United States', 'Japan'])
        self.assertEqual([region['visits'] for region in payload['overseas']], [5, 1])

    def test_totals_and_internal_split(self):
        payload = build_payload()
        totals = payload['totals']

        self.assertEqual(14, totals['records'])
        self.assertEqual(6, totals['ips'])
        self.assertEqual(2, totals['errors'])
        self.assertEqual(3, totals['domestic_ips'])
        self.assertEqual(6, totals['domestic_visits'])
        self.assertEqual(2, totals['overseas_ips'])
        self.assertEqual(6, totals['overseas_visits'])
        self.assertEqual(1, totals['internal_ips'])
        self.assertEqual(2, totals['domestic_regions'])
        self.assertEqual(2, totals['overseas_regions'])
        self.assertEqual(['127.0.0.1', '10.0.0.1'][:1],
                         [entry[0] for entry in payload['internal']['entries']])
        self.assertEqual(2, payload['internal']['visits'])

    def test_region_entries_are_compact_and_sorted(self):
        payload = build_payload()
        entries = payload['domestic'][0]['entries']

        self.assertEqual(['1.1.1.1', 3, ['hyper'], f'{day(3)} 12:00:00'], entries[0])
        self.assertEqual(['2.2.2.2', 1, [], f'{day(3)} 13:00:00'], entries[1])
        self.assertEqual('浙江省 · 杭州市',
                         payload['domestic'][0]['label'].split(' ', 1)[1])

    def test_top_lists_and_trend(self):
        payload = build_payload()

        self.assertEqual('4.4.4.4', payload['top_ips'][0]['ip'])
        self.assertEqual(5, payload['top_ips'][0]['visits'])
        self.assertEqual('/', payload['top_paths'][0]['path'])
        self.assertEqual(8, payload['top_paths'][0]['visits'])
        self.assertEqual(30, len(payload['daily']))
        self.assertEqual(day(0), payload['daily'][-1]['date'])
        self.assertEqual(2, payload['daily'][-1]['visits'])
        self.assertEqual(6, payload['daily'][-3]['visits'])


class HttpFixture(unittest.TestCase):
    """启动一个真实 HTTP 服务（不写访问记录）用于接口测试。"""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        # 与 test_http_security 相同：绕过访问统计，避免测试流量写入 site.db。
        self.guard = patch.object(main.BeautifulDirectoryHandler, 'handle_one_request',
                                  BaseHTTPRequestHandler.handle_one_request)
        self.guard.start()
        self.addCleanup(self.guard.stop)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(
            main.BeautifulDirectoryHandler, directory=str(Path(self.temp.name))))
        self.addCleanup(self.server.server_close)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.shutdown)

    def get_json(self, path):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_address[1], timeout=10)
        try:
            connection.request('GET', path)
            response = connection.getresponse()
            return response.status, json.loads(response.read() or b'{}')
        finally:
            connection.close()


class IpDetailTests(unittest.TestCase):
    def test_invalid_ip_returns_none(self):
        self.assertIsNone(visitor.build_ip_detail('not-an-ip', records=[]))
        self.assertIsNone(visitor.build_ip_detail('', records=[]))

    def test_detail_is_paged_and_newest_first(self):
        with patch.object(visitor, 'region_label', side_effect=lambda ip: REGION_MAP[ip]):
            detail = visitor.build_ip_detail('4.4.4.4', records=RECORDS, limit=2, offset=0)

        self.assertEqual(5, detail['totals']['records'])
        self.assertEqual(2, len(detail['records']))
        self.assertTrue(detail['has_more'])
        self.assertEqual(f'{day(2)} 12:00:00', detail['records'][0]['time'])
        self.assertEqual(f'{day(2)} 11:00:00', detail['records'][1]['time'])
        self.assertEqual([{'method': 'GET', 'visits': 5}], detail['totals']['methods'])
        self.assertEqual(2, detail['totals']['paths'])
        self.assertEqual({'path': '/', 'visits': 4, 'errors': 0}, detail['paths'][0])
        self.assertEqual('United States', detail['location']['country'])

    def test_detail_marks_internal_and_errors(self):
        detail = visitor.build_ip_detail('127.0.0.1', records=RECORDS, limit=10)

        self.assertTrue(detail['internal'])
        self.assertEqual('🏠 内网', detail['region'])
        self.assertEqual(['hyper'], detail['totals']['users'])
        self.assertEqual(2, detail['totals']['records'])


class VisitStatsEndpointTests(HttpFixture):
    def test_anonymous_request_is_rejected(self):
        with patch.object(main, 'VISIT_STATS_REQUIRE_LOGIN', True), \
                patch.object(main, 'VISIT_STATS_ALLOWED_USERS', set()):
            status, payload = self.get_json('/api/visit-stats')

        self.assertEqual(401, status)
        self.assertTrue(payload['need_login'])

    def test_payload_carries_viewer_permission(self):
        stub = {'totals': {'records': 1}, 'daily': [], 'domestic': []}
        with patch.object(main, 'VISIT_STATS_REQUIRE_LOGIN', False), \
                patch.object(main, 'get_user_info_from_request',
                             return_value={'username': 'hyper'}), \
                patch('src.analyze_visitor.get_stats_payload', return_value=stub) as mocked:
            status, payload = self.get_json('/api/visit-stats')

        self.assertEqual(200, status)
        self.assertEqual({'username': 'hyper', 'can_view_detail': True}, payload['viewer'])
        self.assertEqual(stub, {key: value for key, value in payload.items() if key != 'viewer'})
        mocked.assert_called_once_with(refresh=False)

    def test_viewer_without_permission_cannot_open_detail(self):
        stub = {'totals': {}, 'daily': [], 'domestic': []}
        with patch.object(main, 'VISIT_STATS_REQUIRE_LOGIN', False), \
                patch.object(main, 'get_user_info_from_request',
                             return_value={'username': 'caibo'}), \
                patch('src.analyze_visitor.get_stats_payload', return_value=stub):
            status, payload = self.get_json('/api/visit-stats')

        self.assertEqual(200, status)
        self.assertFalse(payload['viewer']['can_view_detail'])


class VisitDetailEndpointTests(HttpFixture):
    def test_detail_requires_login(self):
        with patch.object(main, 'get_user_info_from_request', return_value={}):
            status, payload = self.get_json('/api/visit-detail?ip=1.1.1.1')

        self.assertEqual(401, status)
        self.assertTrue(payload['need_login'])

    def test_detail_rejects_other_accounts(self):
        with patch.object(main, 'get_user_info_from_request', return_value={'username': 'caibo'}):
            status, payload = self.get_json('/api/visit-detail?ip=1.1.1.1')

        self.assertEqual(403, status)
        self.assertIn('hyper', payload['error'])

    def test_detail_returns_records_for_hyper(self):
        stub = {'ip': '1.1.1.1', 'totals': {'records': 1}, 'records': [], 'has_more': False}
        with patch.object(main, 'get_user_info_from_request',
                          return_value={'username': 'Hyper'}), \
                patch('src.analyze_visitor.build_ip_detail', return_value=stub) as mocked:
            status, payload = self.get_json('/api/visit-detail?ip=1.1.1.1&limit=50&offset=10')

        self.assertEqual(200, status)
        self.assertEqual(stub, payload)
        mocked.assert_called_once_with('1.1.1.1', limit=50, offset=10)

    def test_detail_rejects_invalid_ip(self):
        with patch.object(main, 'get_user_info_from_request',
                          return_value={'username': 'hyper'}):
            status, payload = self.get_json('/api/visit-detail?ip=not-an-ip')

        self.assertEqual(400, status)
        self.assertIn('无效', payload['error'])


if __name__ == '__main__':
    unittest.main()
