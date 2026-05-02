from backend.app.normalizer import normalize_streams
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
