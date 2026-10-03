from app.intelligence.detector import Anomaly
from app.intelligence.rca import rank
from tests.test_graph import g


class NoHistory:
    def support(self, e):
        return 0.0

    def count(self, e):
        return 0


A = lambda e, m, v, b, s, t: Anomaly(e, m, v, b, s, t, t)


def test_congestion_ranks_uplink_first():
    an = [
        A("link-r1-sw1", "link_utilization", 97, 14, 1.0, 100),
        A("link-r1-sw1", "link_latency_ms", 86, 2.5, 1.0, 102),
        A("svc-web", "http_latency_ms", 1450, 42, 1.0, 106),
        A("svc-dns", "dns_success_rate", 72, 100, 0.5, 108),
    ]
    top, conf = rank(an, ["svc-web", "svc-dns"], g, NoHistory())
    assert top[0].entity_id == "link-r1-sw1" and conf >= 0.8
    assert any(c.suppressed_by == "link-r1-sw1" for c in top[1:])


def test_dns_failure_ranks_dns_first():
    an = [
        A("svc-dns", "dns_success_rate", 0, 100, 1.0, 100),
        A("svc-web", "http_ok", 0, 1, 1.0, 102),
    ]
    top, _ = rank(an, ["svc-web", "svc-dns"], g, NoHistory())
    assert top[0].entity_id == "svc-dns"


def test_cpu_spike_ranks_server_first():
    an = [
        A("app01", "cpu_percent", 98, 18, 1.0, 100),
        A("svc-web", "http_latency_ms", 1100, 42, 1.0, 104),
    ]
    top, _ = rank(an, ["svc-web"], g, NoHistory())
    assert top[0].entity_id == "app01"


def test_isolated_anomaly_without_service_impact_is_low_confidence():
    an = [A("link-dist-a-sw2", "link_utilization", 90, 6, 1.0, 100)]
    _, conf = rank(an, [], g, NoHistory())
    assert conf < 0.55
