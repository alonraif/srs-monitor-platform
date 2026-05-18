from backend.app.normalizer import normalize_clients, normalize_streams
from backend.app.srs_client import SrsApiSnapshot


def test_normalize_streams_from_srs_snapshot():
    snapshot = SrsApiSnapshot(
        base_url="http://srs:1985",
        reachable=True,
        responses={
            "streams": {
                "code": 0,
                "streams": [
                    {
                        "id": "s1",
                        "name": "program",
                        "app": "live",
                        "publish": {"active": True, "ip": "203.0.113.10"},
                        "kbps": {"recv_30s": 4500},
                        "video": {"codec": "h264", "width": 1920, "height": 1080, "fps": 50},
                        "audio": {"codec": "aac"},
                        "clients": 20,
                    }
                ],
            }
        },
        errors={},
    )

    streams = normalize_streams(snapshot)
    assert len(streams) == 1
    stream = streams[0]
    assert stream.id == "s1"
    assert stream.app == "live"
    assert stream.stream_key == "program"
    assert stream.metrics.bitrate_kbps == 4500
    assert stream.metrics.resolution == "1920x1080"
    assert stream.source_ip == "203.0.113.10"


def test_viewer_counts_exclude_internal_probe_clients():
    snapshot = SrsApiSnapshot(
        base_url="http://srs:1985",
        reachable=True,
        responses={
            "streams": {
                "code": 0,
                "streams": [
                    {
                        "id": "live/feed-1",
                        "name": "feed-1",
                        "app": "live",
                        "publish": {"active": True, "ip": "203.0.113.10"},
                        "kbps": {"recv_30s": 4500},
                        "video": {"codec": "h264", "width": 1920, "height": 1080, "fps": 50},
                        "audio": {"codec": "aac"},
                    }
                ],
            },
            "clients": {
                "code": 0,
                "clients": [
                    {
                        "id": "viewer-1",
                        "stream": "live/feed-1",
                        "publish": False,
                        "type": "play",
                        "ip": "198.51.100.20",
                        "alive": 25,
                        "agent": "Mozilla/5.0",
                    },
                    {
                        "id": "probe-1",
                        "stream": "live/feed-1",
                        "publish": False,
                        "type": "play",
                        "ip": "10.0.0.7",
                        "alive": 12,
                        "agent": "Lavf/60.3.100",
                    },
                ],
            },
        },
        errors={},
    )

    streams = normalize_streams(snapshot)
    clients = normalize_clients(snapshot)
    assert streams[0].viewers_current == 1
    assert len(clients) == 1
    assert clients[0].id == "viewer-1"


def test_viewer_counts_exclude_internal_multiview_rtc_play():
    snapshot = SrsApiSnapshot(
        base_url="http://srs:1985",
        reachable=True,
        responses={
            "streams": {
                "code": 0,
                "streams": [
                    {
                        "id": "vid-q3xnt26",
                        "name": "SRT-Test",
                        "app": "live",
                        "publish": {"active": True, "ip": "172.16.32.1"},
                    }
                ],
            },
            "clients": {
                "code": 0,
                "clients": [
                    {
                        "id": "4916j9nr",
                        "stream": "vid-q3xnt26",
                        "ip": "172.16.32.11",
                        "pageUrl": "",
                        "tcUrl": "webrtc://172.16.32.84/live",
                        "type": "rtc-play",
                        "publish": False,
                        "alive": 61.63,
                        "agent": "unknown",
                    }
                ],
            },
        },
        errors={},
    )

    streams = normalize_streams(snapshot)
    clients = normalize_clients(snapshot)
    assert streams[0].viewers_current == 0
    assert len(clients) == 0
