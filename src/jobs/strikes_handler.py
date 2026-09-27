import logging

from src.utils.log_setup import logger


class StrikesHandler:
    def __init__(self, job_name, arr, max_strikes, event_bus=None):
        self.job_name = job_name
        self.arr = arr
        self.tracker = arr.tracker
        self.max_strikes = max_strikes
        self.event_bus = event_bus
        self.tracker.defective.setdefault(job_name, {})

    def filter_strike_exceeds(self, affected_downloads, queue):
        recovered, removed_from_queue, paused = self._recover_downloads(
            affected_downloads, queue
        )
        strike_exceeds = self._apply_strikes_and_filter(affected_downloads)
        if logger.isEnabledFor(logging.DEBUG):
            self.log_change(recovered, removed_from_queue, paused, strike_exceeds)
        return strike_exceeds

    def get_entry(self, download_id):
        return self.tracker.defective[self.job_name].get(download_id)

    def pause_entry(self, download_id, reason):
        entry = self.get_entry(download_id)
        if entry:
            entry["tracking_paused"] = True
            entry["pause_reason"] = reason
            logger.debug(
                "strikes_handler.py/StrikesHandler/pause_entry: Paused tracking for %s due to: %s",
                download_id,
                reason,
            )

    def unpause_entry(self, download_id):
        entry = self.get_entry(download_id)
        if entry:
            entry.pop("tracking_paused", None)
            entry.pop("pause_reason", None)
            logger.debug(
                "strikes_handler.py/StrikesHandler/unpause_entry: Unpaused tracking for %s",
                download_id,
            )

    # pylint: disable=too-many-locals, too-many-branches
    def log_change(self, recovered, removed_from_queue, paused, strike_exceeds):
        """
        Logs changes in strike tracking:
        - Added = Downloads caught for first time (1 strike)
        - Incremented = Downloads caught previously (>1 strikes)
        - Recovered = Downloads caught previously but now no longer (as they recovered)
        - removed_from_queue = Downloads caught previously but now no longer (as they are no longer in queue)
        - Paused = Downloads flagged as paused for tracking
        - strike_exceeds = Downloads that have too many strikes
        """
        tracker = self.tracker.defective[self.job_name]

        added = []
        incremented = []
        paused_entries = []
        recovered_entries = []
        removed_entries = []
        strike_exceeded = []

        for d_id, entry in tracker.items():
            entry = tracker.get(d_id, {})
            strikes = entry.get("strikes")
            if d_id in paused:
                reason = entry.get("pause_reason", "unknown reason")
                paused_entries.append(
                    f"'{d_id}' [{strikes}/{self.max_strikes}, {reason}]"
                )
            elif d_id in strike_exceeds:
                strike_exceeded.append(f"'{d_id}' [{strikes}/{self.max_strikes}]")
            elif strikes == 1:
                added.append(d_id)
            elif strikes > 1:
                incremented.append(f"'{d_id}' [{strikes}/{self.max_strikes}]")

        for d_id in recovered:
            recovered_entries.append(d_id)

        for d_id in removed_from_queue:
            removed_entries.append(d_id)

        log_lines = [
            f"strikes_handler.py/log_change/defective tracker '{self.job_name}':"
        ]

        if added:
            log_lines.append(f"Added ({len(added)}): {', '.join(added)}")
        if incremented:
            log_lines.append(
                f"Incremented ({len(incremented)}) [strikes]: {', '.join(incremented)}"
            )
        if paused_entries:
            log_lines.append(
                f"Tracking Paused ({len(paused_entries)}) [strikes, reason]: {', '.join(paused_entries)}"
            )
        if removed_entries:
            log_lines.append(
                f"Removed from queue ({len(removed_entries)}): {', '.join(removed_entries)}"
            )
        if recovered_entries:
            log_lines.append(
                f"Recovered ({len(recovered_entries)}): {', '.join(recovered_entries)}"
            )
        if strike_exceeded:
            log_lines.append(
                f"Strikes Exceeded ({len(strike_exceeded)}): {', '.join(strike_exceeded)}"
            )

        logger.debug("\n".join(log_lines))

        return added, incremented, paused, recovered, strike_exceeds, removed_from_queue

    def _recover_downloads(self, affected_downloads, queue):
        """
        Identifies downloads that were previously tracked and are now no longer affected as recovered.
        If a download is marked as tracking_paused, they are not recovered (will be recovered later potentially)
        """
        recovered = []
        removed_from_queue = []
        paused = {}
        job_tracker = self.tracker.defective[self.job_name]
        affected_ids = dict(affected_downloads)
        queue_download_ids = {item.get("downloadId") for item in queue}

        for d_id, entry in list(job_tracker.items()):
            if d_id not in affected_ids:
                if entry.get("tracking_paused", False):
                    pause_reason = entry.get("pause_reason", None)
                    logger.debug(
                        "strikes_handler.py/_recover_downloads: %s tracking is paused for this entry: %s (%s). Reason: %s",
                        self.job_name,
                        entry["title"],
                        d_id,
                        pause_reason,
                    )
                    paused[d_id] = pause_reason
                else:
                    if d_id in queue_download_ids:
                        recovery_reason = "has recovered"
                        log_level = logger.info
                        recovered.append(d_id)
                    elif d_id in self.tracker.deleted:
                        recovery_reason = "deleted in previous round"
                        log_level = logger.debug
                        removed_from_queue.append(d_id)
                    else:
                        recovery_reason = "no longer in queue"
                        log_level = logger.verbose
                        removed_from_queue.append(d_id)

                    log_level(
                        f">>> Job '{self.job_name,}' no longer flagging download (download {recovery_reason}): {entry['title']}"
                    )
                    del job_tracker[d_id]

        return recovered, removed_from_queue, paused

    def _apply_strikes_and_filter(self, affected_downloads):
        for d_id, affected_download in list(affected_downloads.items()):
            title = affected_download["title"]
            strikes = self._increment_strike(d_id, title)
            strikes_left = self.max_strikes - strikes
            self._log_strike_status(title, strikes, strikes_left)

            # Emit strike event (fire-and-forget via stored task reference)
            if self.event_bus:
                import asyncio
                from src.web.events import Event, EventType
                try:
                    asyncio.ensure_future(self.event_bus.emit(Event(EventType.STRIKE_APPLIED, {
                        "arr_name": self.arr.name,
                        "arr_type": self.arr.arr_type,
                        "job_name": self.job_name,
                        "download_id": d_id,
                        "title": title,
                        "strikes": strikes,
                        "max_strikes": self.max_strikes,
                    })))
                except Exception:
                    pass

            if strikes_left >= 0:
                del affected_downloads[d_id]

        return affected_downloads

    def _increment_strike(self, d_id, title):
        entry = self.tracker.defective[self.job_name].setdefault(
            d_id,
            {"title": title, "strikes": 0},
        )
        entry["strikes"] += 1
        return entry["strikes"]

    def _log_strike_status(self, title, strikes, strikes_left):
        # -1 is the first time no strikes are remaining and thus removal will be triggered
        # Since the removal itself sparks an appropriate message, we don't need to show the message again here on info-level
        # Thus putting it to verbose level
        log_level = logger.verbose if strikes_left == -1 else logger.info

        will_trigger_removal = " -> too many" if strikes_left < 0 else ""

        log_level(
            ">>> Job '%s' flagged download (%s/%s strikes%s): %s",
            self.job_name,
            strikes,
            self.max_strikes,
            will_trigger_removal,
            title,
        )

        if strikes_left <= -2:  # noqa: PLR2004
            logger.info(
                '>>> 💡 Tip: Since this download should already have been removed in a previous iteration but keeps coming back, this indicates the blocking of the torrent does not work correctly. Consider turning on the option "Reject Blocklisted Torrent Hashes While Grabbing" on the indexer in the *arr app: %s',
                title,
            )
