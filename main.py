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
from src.web.events import EventBus, NoOpEventBus, Event, EventType

settings = Settings()

# Event bus for web UI integration
web_enabled = settings.web.enabled
event_bus = EventBus() if web_enabled else NoOpEventBus()
trigger_event = asyncio.Event() if web_enabled else None

job_manager = JobManager(settings, event_bus=event_bus)
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

    # Wait for the next run, but allow manual trigger to interrupt
    if trigger_event:
        try:
            await asyncio.wait_for(
                trigger_event.wait(),
                timeout=settings.general.timer * 60,
            )
            trigger_event.clear()
            logger.info("Manual trigger received, starting cycle early")
        except asyncio.TimeoutError:
            pass
    else:
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

        await event_bus.emit(Event(EventType.CYCLE_START, {
            "instances": [arr.name for arr in settings.instances],
        }))

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
            try:
                await job_manager.run_jobs(arr)
            except Exception as e:
                logger.error(f"Error running jobs on {arr.name}: {e}")
            logger.verbose("")

        # Run download client jobs (these run independently of *arr instances)
        try:
            await job_manager.run_download_client_jobs()
        except Exception as err:  # noqa: BLE001
            logger.error(
                f"Error while running download-client jobs: {err}",
                exc_info=True,
            )

        await event_bus.emit(Event(EventType.CYCLE_END, {
            "instances": [arr.name for arr in settings.instances],
        }))

        # Wait for the next run
        await wait_next_run()


async def main_with_restart():
    """Run main loop with automatic restart on unexpected failures."""
    while True:
        try:
            await main()
        except SystemExit as e:
            if e.code == 0:
                raise  # Clean shutdown (e.g. SIGTERM), don't restart
            logger.error("Main loop exited (unreachable service). Restarting in 30 seconds...")
            await asyncio.sleep(30)
        except Exception as e:
            logger.error(f"Main loop crashed: {e}. Restarting in 30 seconds...")
            await asyncio.sleep(30)


async def start():
    """Entry point that optionally runs web server alongside main loop."""
    if web_enabled:
        from src.web.app import start_web_server
        web_task = asyncio.create_task(
            start_web_server(settings, event_bus, trigger_event)
        )
        main_task = asyncio.create_task(main_with_restart())
        await asyncio.gather(main_task, web_task)
    else:
        await main_with_restart()


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, terminate)
    asyncio.run(start())
