from src.jobs.removal_job import RemovalJob


class RemoveMetadataMissing(RemovalJob):
    queue_scope = "full"
    blocklist = True

    async def _find_affected_items(self):
        # qBittorrent surfaces a dedicated *arr error message while fetching metadata.
        conditions = [("queued", "qBittorrent is downloading metadata")]
        affected_items = self.queue_manager.filter_queue(self.queue, conditions)

        # Other clients (e.g. Transmission, Deluge) do not surface such a message, so a
        # torrent stuck fetching metadata is invisible to the message-based check above
        # (see #57). Opt-in fallback: also flag queued items whose size is not yet known
        # (size == 0), which is the client-agnostic signature of "no metadata yet".
        # Keep this fallback on the normal queue so widening the exact-message check to
        # the full queue does not make unrelated full-only size-zero items eligible.
        # Debounced by max_strikes like the rest of this job.
        if getattr(self.job, "detect_via_missing_size", False):
            normal_queue = await self.queue_manager.get_queue_items(
                queue_scope="normal"
            )
            seen = {(item.get("id"), item.get("downloadId")) for item in affected_items}
            for item in self.queue_manager.filter_missing_size(normal_queue):
                item_identity = (item.get("id"), item.get("downloadId"))
                if item_identity not in seen:
                    affected_items.append(item)
                    seen.add(item_identity)

        return affected_items
