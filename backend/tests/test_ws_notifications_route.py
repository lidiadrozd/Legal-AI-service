from app.main import app


def test_notification_websocket_route_registered():
    paths = [getattr(route, "path", None) for route in app.routes]
    assert "/ws/notifications" in paths
