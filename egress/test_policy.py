import unittest
from policy import validate_networks, validate_domains, blocked_set, host_policy, namespace_policy, dns_denial_evidence

V = dict(private="172.31.240.0/28", outbound="172.31.240.16/28",
         app="172.31.240.2", proxy="172.31.240.3", ext="172.31.240.18",
         gateway="172.31.240.17", uplink="eth0")

class PolicyTests(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(validate_networks(V), V)
    def test_invalid_networks(self):
        for changes in ({"outbound": V["private"]}, {"app": V["proxy"]},
                        {"app": "172.31.240.0"}, {"app": "172.31.240.17"},
                        {"private": "8.8.8.0/24"}, {"uplink": 'eth0"; flush ruleset'}):
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    validate_networks({**V, **changes})
    def test_domain_list(self):
        self.assertEqual(validate_domains("alexa.amazon.es\n"), ["alexa.amazon.es"])
        for bad in ("", "*.amazon.es", ".amazon.es", "amazon.es.example.org",
                    "1.1.1.1", "alexa.amazon.es:443", "alexa.amazon.es\nalexa.amazon.es"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    validate_domains(bad)
    def test_network_namespace_default_deny(self):
        app = namespace_policy(V)
        self.assertIn("hook output priority -150; policy drop", app)
        self.assertIn("hook input priority -150; policy drop", app)
        self.assertIn("hook forward priority -150; policy drop", app)
        self.assertEqual(app.count(" accept\n"), 2)
        self.assertNotIn("dport 53 accept", app)
        self.assertIn("udp dport 53 counter name dns_docker_udp drop", app)
        self.assertIn("udp dport 53 counter name dns_public_udp drop", app)
        self.assertNotIn("dport 443", app)
        self.assertIn("ip daddr " + V["proxy"] + " tcp dport 3128", app)
    def test_dns_evidence(self):
        before = {"dns_docker_udp": 3, "dns_public_udp": 5}
        self.assertEqual(dns_denial_evidence(before, before, False),
                         {"DNS_GUARD_DOCKER": False, "DNS_GUARD_PUBLIC": False})
        self.assertEqual(dns_denial_evidence(before, before, True),
                         {"DNS_GUARD_DOCKER": False, "DNS_GUARD_PUBLIC": True})
        self.assertEqual(dns_denial_evidence(before,
                         {"dns_docker_udp": 4, "dns_public_udp": 5}, True),
                         {"DNS_GUARD_DOCKER": True, "DNS_GUARD_PUBLIC": True})
        self.assertEqual(dns_denial_evidence(before,
                         {"dns_docker_udp": 4, "dns_public_udp": 6}, False),
                         {"DNS_GUARD_DOCKER": True, "DNS_GUARD_PUBLIC": True})
    def test_proxy_policy(self):
        policy = namespace_policy(V, True, ["8.8.8.0/24"])
        self.assertIn("8.8.8.0/24", policy)
        self.assertIn("ip saddr " + V["ext"] + " tcp dport 443 accept", policy)
        self.assertLess(policy.index("ip daddr @blocked4 drop"), policy.index("tcp dport 443 accept"))
    def test_host_scoped(self):
        policy = host_policy(V)
        self.assertNotIn("flush ruleset", policy)
        self.assertIn("create table inet alexa_guard", policy)
        self.assertIn("hook input priority -10; policy accept", policy)
        self.assertIn("hook forward priority -10; policy accept", policy)
        self.assertIn('oifname "eth0"', policy)
        self.assertIn('iifname "br-alexa-priv" counter drop', policy)
        self.assertIn('oifname "br-alexa-egress" counter drop', policy)
    def test_blocked_ranges(self):
        policy = blocked_set(["8.8.8.0/24"])
        for value in ("10.0.0.0/8", "127.0.0.0/8", "169.254.0.0/16", "8.8.8.0/24"):
            self.assertIn(value, policy)

if __name__ == "__main__":
    unittest.main()
