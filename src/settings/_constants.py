import os

from src.settings._config_as_yaml import get_config_as_yaml


class Envs:
    def __init__(self):
        self.in_docker = os.environ.get("IN_DOCKER", "").lower() == "true"
        self.image_tag = os.environ.get("IMAGE_TAG") or "Local"
        self.short_commit_id = os.environ.get("SHORT_COMMIT_ID") or "n/a"
        self.use_config_yaml = False  # Overwritten later if config file exists

    def config_as_yaml(self):
        return get_config_as_yaml(vars(self), internal_attributes={"in_docker"})


class Paths:
    logs = "./logs/logs.txt"
    config_file = "./config/config.yaml"


class ApiEndpoints:
    radarr = "/api/v3"
    sonarr = "/api/v3"
    sportarr = "/api/v3"
    lidarr = "/api/v1"
    readarr = "/api/v1"
    whisparr = "/api/v3"
    qbittorrent = "/api/v2"


class MinVersions:
    radarr = "5.10.3.9171"
    sonarr = "4.0.9.2332"
    sportarr = "4.0.0.0"
    lidarr = "2.11.1.4621"
    readarr = "0.4.15.2787"
    whisparr = "2.0.0.548"
    qbittorrent = "4.3.0"
    sabnzbd = "4.0.0"


class FullQueueParameter:
    radarr = "includeUnknownMovieItems"
    sonarr = "includeUnknownSeriesItems"
    sportarr = "includeUnknownSeriesItems"
    lidarr = "includeUnknownArtistItems"
    readarr = "includeUnknownAuthorItems"
    whisparr = "includeUnknownSeriesItems"


class DetailItemKey:
    radarr = "movie"
    sonarr = "episode"
    sportarr = "episode"
    lidarr = "album"
    readarr = "book"
    whisparr = "episode"


class DetailItemSearchCommand:
    radarr = "MoviesSearch"
    sonarr = "EpisodeSearch"
    sportarr = "EpisodeSearch"
    lidarr = "AlbumSearch"
    readarr = "BookSearch"
    whisparr = None


class RefreshItemKey:
    radarr = "movie"
    sonarr = "series"
    sportarr = "series"


class RefreshItemCommand:
    radarr = "RefreshMovie"
    sonarr = "RefreshSeries"
    sportarr = "RefreshSeries"
