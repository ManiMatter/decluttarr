from types import SimpleNamespace

from src.settings._download_clients import DownloadClients


def _clients(qbits):
    """A DownloadClients instance with the given qbit list (bypassing __init__)."""
    dc = DownloadClients.__new__(DownloadClients)
    dc.qbittorrent = qbits
    dc.sabnzbd = []
    return dc


def test_ready_only_returns_ready_client():
    client = SimpleNamespace(name="qBittorrent", ready=True)
    dc = _clients([client])
    assert dc.get_download_client_by_name("qBittorrent", ready_only=True) == (
        client,
        "qbittorrent",
    )


def test_ready_only_skips_not_ready_client():
    client = SimpleNamespace(name="qBittorrent", ready=False)
    dc = _clients([client])
    # A degraded client is treated as unavailable so jobs never call it.
    assert dc.get_download_client_by_name("qBittorrent", ready_only=True) == (
        None,
        None,
    )


def test_default_ignores_readiness():
    # Backward compatibility: without ready_only, readiness is not considered.
    client = SimpleNamespace(name="qBittorrent", ready=False)
    dc = _clients([client])
    assert dc.get_download_client_by_name("qBittorrent") == (client, "qbittorrent")


def test_unknown_name_returns_none():
    client = SimpleNamespace(name="qBittorrent", ready=True)
    dc = _clients([client])
    assert dc.get_download_client_by_name("does-not-exist", ready_only=True) == (
        None,
        None,
    )
