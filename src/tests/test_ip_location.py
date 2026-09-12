import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from src import ip_location as geo

class IpLocationTests(unittest.TestCase):
    def tearDown(self):
        geo._lookup.cache_clear()

    def test_xdb_fields(self):
        self.assertEqual(geo._parse_region("中国|广东省|深圳市|电信|CN"),
                         ("中国", "广东省", "深圳市", "电信"))
        self.assertEqual(geo._parse_region("United States|0|0|0|US"),
                         ("United States", "未知", "未知", ""))

    def test_ipv6_fused_fields(self):
        self.assertEqual(geo._parse_region("亚洲|中国|浙江省|||移动|宽带", 6),
                         ("中国", "浙江省", "未知", "移动"))
        self.assertEqual(geo._parse_region("亚洲|中国|重庆市|重庆城区|沙坪坝区|电信|基站", 6),
                         ("中国", "重庆市", "重庆城区", "电信"))

    def test_private_and_invalid(self):
        for ip, city in [("::1", "本地"), ("127.0.0.1", "本地"),
                         ("fd00::1", "内网"), ("fe80::1", "内网"),
                         ("::ffff:192.168.1.1", "内网"), ("bad", "未知城市")]:
            self.assertEqual(geo.query_ip_city(ip), city)

    def test_missing_database(self):
        with patch.dict(geo._searchers, {4: None, 6: None}, clear=True):
            self.assertEqual(geo.query_ip_city("8.8.4.4"), "未知城市")
            self.assertEqual(geo.query_ip_city("2001:4860:4860::8844"), "未知城市")

    def test_fallback_and_cache_isolation(self):
        with patch.object(geo, "_get_searcher") as factory:
            factory.return_value.search.return_value = "Australia|Queensland|0|0|AU"
            self.assertEqual(geo.query_ip_city("1.2.3.4"), "Queensland")
            result = geo.query_ip_location("1.2.3.4")
            result["region"] = "changed"
            self.assertEqual(geo.query_ip_location("1.2.3.4")["region"], "Queensland")

    def test_real_databases_and_concurrency(self):
        ips = ["8.8.8.8", "113.118.113.77", "2001:4860:4860::8888",
               "240e:3b7:3272:d8d0:db09:c067:8d59:539e"]
        expected = [geo.query_ip_location(ip) for ip in ips]
        self.assertTrue(all(row["country"] != "未知" for row in expected))
        self.assertEqual(geo.query_ip_location("::ffff:8.8.8.8"), expected[0])
        def uncached(ip):
            return geo._lookup.__wrapped__(ip)
        with ThreadPoolExecutor(max_workers=8) as pool:
            actual = list(pool.map(uncached, ips * 20))
        self.assertEqual(actual, [tuple(row.values()) for row in expected] * 20)

if __name__ == "__main__":
    unittest.main()
