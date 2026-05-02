from backend.app.alarm_engine import AlarmEngine


def test_source_ip_match_exact_and_cidr():
    engine = AlarmEngine()
    assert engine._source_ip_matches("203.0.113.10", "203.0.113.10")
    assert engine._source_ip_matches("203.0.113.0/24", "203.0.113.44")
    assert not engine._source_ip_matches("203.0.113.0/24", "198.51.100.2")
    assert engine._source_ip_matches("unknown", "198.51.100.2")
