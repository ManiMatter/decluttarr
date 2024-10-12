from src.utils.shared import (
    errorDetails,
    rest_get,
    rest_post,
    get_queue,
    get_arr_records,
)
import logging, verboselogs
from datetime import datetime, timedelta, timezone
import dateutil.parser

logger = verboselogs.VerboseLogger(__name__)


async def run_periodic_rescans(
    settingsDict,
    BASE_URL,
    API_KEY,
    NAME,
    arr_type,
):
    # Checks the wanted items and runs scans
    if not arr_type in settingsDict["RUN_PERIODIC_RESCANS"]:
        return
    try:
        queue = await get_queue(BASE_URL, API_KEY)
        check_on_endpoint = []
        RESCAN_SETTINGS = settingsDict["RUN_PERIODIC_RESCANS"][arr_type]
        if RESCAN_SETTINGS["MISSING"]:
            check_on_endpoint.append("missing")
        if RESCAN_SETTINGS["CUTOFF_UNMET"]:
            check_on_endpoint.append("cutoff")

        params = {"sortDirection": "ascending"}
        if arr_type == "SONARR":
            params["sortKey"] = "episodes.lastSearchTime"
            queue_ids = [r["seriesId"] for r in queue if "seriesId" in r]
            series = await rest_get(f"{BASE_URL}/series", API_KEY)
            series_dict = {s["id"]: s for s in series}

        elif arr_type == "RADARR":
            params["sortKey"] = "movies.lastSearchTime"
            queue_ids = [r["movieId"] for r in queue if "movieId" in r]

        for end_point in check_on_endpoint:
            records = await get_arr_records(
                BASE_URL, API_KEY, params=params, end_point=f"wanted/{end_point}"
            )
            if records is None:
                logger.verbose(
                    f">>> Rescan: No {end_point} items, thus nothing to rescan."
                )
                continue

            # Filter out items that are already being downloaded (are in queue)
            records = [r for r in records if r["id"] not in queue_ids]
            if records is None:
                logger.verbose(
                    f">>> Rescan: All {end_point} items are already being downloaded, thus nothing to rescan."
                )
                continue

            # Remove records that have recently been searched already
            for record in reversed(records):
                if not (
                    ("lastSearchTime" not in record)
                    or (
                        (
                            dateutil.parser.isoparse(record["lastSearchTime"])
                            + timedelta(days=RESCAN_SETTINGS["MIN_DAYS_BEFORE_RESCAN"])
                        )
                        < datetime.now(timezone.utc)
                    )
                ):
                    records.remove(record)

            # Select oldest records
            records = records[: RESCAN_SETTINGS["MAX_CONCURRENT_SCANS"]]

            if not records:
                logger.verbose(
                    f">>> Rescan: All {end_point} items have recently been scanned for, thus nothing to rescan."
                )
                continue

            if arr_type == "SONARR":
                for record in records:
                    series_id = record.get("seriesId")
                    if series_id and series_id in series_dict:
                        record["series"] = series_dict[series_id]
                    else:
                        record["series"] = (
                            None  # Or handle missing series info as needed
                        )

                logger.verbose(
                    f">>> Running a scan for {len(records)} {end_point} items:\n"
                    + "\n".join(
                        [
                            f"{episode['series']['title']} (Season {episode['seasonNumber']} / Episode {episode['episodeNumber']} / Aired: {episode['airDate']}): {episode['title']}"
                            for episode in records
                        ]
                    )
                )
                json = {
                    "name": "EpisodeSearch",
                    "episodeIds": [r["id"] for r in records],
                }

            elif arr_type == "RADARR":
                logger.verbose(
                    f">>> Running a scan for {len(records)} {end_point} items:\n"
                    + "\n".join(
                        [f"{movie['title']} ({movie['year']})" for movie in records]
                    )
                )
                json = {"name": "MoviesSearch", "movieIds": [r["id"] for r in records]}

            if not settingsDict["TEST_RUN"]:
                await rest_post(
                    url=BASE_URL + "/command",
                    json=json,
                    headers={"X-Api-Key": API_KEY},
                )

    except Exception as error:
        errorDetails(NAME, error)
        return 0
