from datetime import datetime, timedelta, timezone

import dateutil.parser
import verboselogs

from src.utils.shared import (
    errorDetails,
    rest_get,
    rest_post,
    get_queue,
    get_arr_records,
)

logger = verboselogs.VerboseLogger(__name__)


async def run_periodic_rescans(
    settingsDict,
    BASE_URL,
    API_KEY,
    NAME,
    arr_type,
):
    # Checks the wanted items and runs scans
    if arr_type not in settingsDict["RUN_PERIODIC_RESCANS"]:
        return

    try:
        queue = await get_queue(BASE_URL, API_KEY, settingsDict)
        RESCAN_SETTINGS = settingsDict["RUN_PERIODIC_RESCANS"][arr_type]

        check_on_endpoint = [
            endpoint for endpoint, enabled in {
                "missing": RESCAN_SETTINGS["MISSING"],
                "cutoff": RESCAN_SETTINGS["CUTOFF_UNMET"],
            }.items() if enabled
        ]

        params = {"sortDirection": "ascending"}

        if arr_type == "SONARR":
            params["sortKey"] = "episodes.lastSearchTime"
            queue_ids = {r["seriesId"] for r in queue if "seriesId" in r}
            series_dict = {s["id"]: s for s in await rest_get(f"{BASE_URL}/series", API_KEY)}

        elif arr_type == "RADARR":
            params["sortKey"] = "movies.lastSearchTime"
            queue_ids = {r["movieId"] for r in queue if "movieId" in r}

        for end_point in check_on_endpoint:
            records = await get_arr_records(
                BASE_URL, API_KEY, params=params, end_point=f"wanted/{end_point}"
            )

            if not records:
                logger.verbose(f">>> Rescan: No {end_point} items, thus nothing to rescan.")
                continue

            # Filter out items already being downloaded
            records = [r for r in records if r["id"] not in queue_ids]

            if not records:
                logger.verbose(f">>> Rescan: All {end_point} items are already being downloaded, thus nothing to rescan.")
                continue

            # Remove records that have been recently searched
            min_rescan_date = datetime.now(timezone.utc) - timedelta(days=RESCAN_SETTINGS["MIN_DAYS_BEFORE_RESCAN"])
            records = [r for r in records if "lastSearchTime" not in r or dateutil.parser.isoparse(r["lastSearchTime"]) < min_rescan_date]

            # Limit number of records based on MAX_CONCURRENT_SCANS
            records = records[: RESCAN_SETTINGS["MAX_CONCURRENT_SCANS"]]

            if not records:
                logger.verbose(f">>> Rescan: All {end_point} items have recently been scanned for, thus nothing to rescan.")
                continue

            # Log and prepare JSON for API request
            if arr_type == "SONARR":
                for record in records:
                    record["series"] = series_dict.get(record.get("seriesId"))

                logger.verbose(
                    f">>> Running a scan for {len(records)} {end_point} items:\n" +
                    "\n".join(
                        f"{episode['series']['title']} (S{episode['seasonNumber']}E{episode['episodeNumber']}, Aired: {episode.get('airDate', 'Unknown')}): {episode['title']}"
                        for episode in records
                    )
                )
                json = {"name": "EpisodeSearch", "episodeIds": [r["id"] for r in records]}

            elif arr_type == "RADARR":
                logger.verbose(
                    f">>> Running a scan for {len(records)} {end_point} items:\n" +
                    "\n".join(f"{movie['title']} ({movie['year']})" for movie in records)
                )
                json = {"name": "MoviesSearch", "movieIds": [r["id"] for r in records]}

            # Execute API request unless in test mode
            if not settingsDict["TEST_RUN"]:
                await rest_post(url=f"{BASE_URL}/command", json=json, headers={"X-Api-Key": API_KEY})

    except Exception as error:
        errorDetails(NAME, error)
        return 0