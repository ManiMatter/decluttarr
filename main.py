import asyncio
import datetime
import signal
import sys
import types

from src.deletion_handler.deletion_handler import WatcherManager
from src.job_manager import JobManager
from src.settings.settings import Settings
from src.utils.log_setup import logger
from src.utils.startup import launch_steps, retry_degraded_instances

settings = Settings()
job_manager = JobManager(settings)
watch_manager = WatcherManager(settings)


def terminate(
    sigterm: signal.SIGTERM,  # noqa: ARG001, pylint: disable=unused-argument
    frame: types.FrameType,  # noqa: ARG001, pylint: disable=unused-argument
) -> None:
    """Terminate cleanly. Needed for respecting 'docker stop'.

    Args:
    ----
        sigterm (signal.Signal): The termination signal.
        frame: The execution frame.

    """

    logger.info(
        f"Termination signal received at {datetime.datetime.now()}."
    )  # noqa: DTZ005
    watch_manager.stop()
    sys.exit(0)


async def wait_next_run():
    # Calculate next run time dynamically (to display)
    next_run = datetime.datetime.now() + datetime.timedelta(
        minutes=settings.general.timer
    )
    formatted_next_run = next_run.strftime("%Y-%m-%d %H:%M")

    logger.verbose(f"*** Done - Next run at {formatted_next_run} ****")

    # Wait for the next run
    await asyncio.sleep(settings.general.timer * 60)


# Main function
async def main():
    await launch_steps(settings)

    if settings.jobs.detect_deletions.enabled:
        await watch_manager.setup()
    # Start Cleaning
    while True:
        logger.info("-" * 50)

        # Give degraded instances a chance to rejoin before this cycle's jobs
        await retry_degraded_instances(settings, watch_manager)

        # Refresh qBit Cookies (SABnzbd doesn't need cookie refresh)
        for qbit in settings.download_clients.qbittorrent:
            if not qbit.ready:
                continue
            try:
                await qbit.refresh_cookie()
            except Exception as err:  # noqa: BLE001
                logger.error(
                    f"Error while refreshing cookie for {qbit.name} ({qbit.base_url}): {err}",
                    exc_info=True,
                )

        # Run script for each instance
        for arr in settings.instances:
            if not arr.ready:  # skip was already logged by retry_degraded_instances
                continue
            await job_manager.run_jobs(arr)
            logger.verbose("")

        # Run download client jobs (these run independently of *arr instances)
        try:
            await job_manager.run_download_client_jobs()
        except Exception as err:  # noqa: BLE001
            logger.error(
                f"Error while running download-client jobs: {err}",
                exc_info=True,
            )

        # Wait for the next run
        await wait_next_run()


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, terminate)
    asyncio.run(main())
