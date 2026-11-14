import warnings

from src.utils.common import wait_and_exit
from src.utils.log_setup import logger


def _all_units(settings):
    """All startup-checked units: download clients and arr instances."""
    return [
        *settings.download_clients.qbittorrent,
        *settings.download_clients.sabnzbd,
        *settings.instances,
    ]


def _unit_label(unit):
    """Printable identity; falls back to arr_type while name is not yet known."""
    name = getattr(unit, "name", None) or getattr(unit, "arr_type", "")
    return f"{name} ({unit.base_url})"


def show_welcome(settings):
    messages = [
        "🎉🎉🎉 Decluttarr - Application Started! 🎉🎉🎉",
        "-" * 80,
        "⭐️ Like this app?",
        "Thanks for giving it a ⭐️ on GitHub!",
        "https://github.com/ManiMatter/decluttarr/",
    ]

    # Show welcome message

    # Show info level tip
    if settings.general.log_level == "INFO":
        messages.extend(
            [
                "",
                "💡 Tip: More logs?",
                "If you want to know more about what's going on, switch log level to 'VERBOSE'",
            ]
        )

    # Show bug report tip
    messages.extend(
        [
            "",
            "🐛 Found a bug?",
            "Before reporting bugs on GitHub, please:",
            "1) Check the readme on github",
            "2) Check open and closed issues on github",
            "3) Switch your logs to 'DEBUG' level",
            "4) Turn off any features other than the one(s) causing it",
            "5) Provide the full logs via pastebin on your GitHub issue",
            "Once submitted, thanks for being responsive and helping debug / re-test",
        ]
    )

    # Show test mode tip
    if settings.general.test_run:
        messages.extend(
            [
                "",
                "=================== IMPORTANT ====================",
                "     ⚠️ ⚠️ ⚠️  TEST MODE IS ACTIVE  ⚠️ ⚠️ ⚠️",
                "Decluttarr won't actually do anything for you...",
                "You can change this via the setting 'test_run'",
                "==================================================",
            ]
        )

    messages.append("")
    # Log all messages at once
    logger.info("\n".join(messages))


async def launch_steps(settings):
    # Hide SSL Verification Warnings
    if not settings.general.ssl_verification:
        warnings.filterwarnings("ignore", message="Unverified HTTPS request")

    logger.verbose(settings)
    show_welcome(settings)

    logger.info("*** Checking Instances ***")
    # Check qbit, fetch initial cookie, and set tag (if needed)
    for qbit in settings.download_clients.qbittorrent:
        await qbit.setup()

    # Check SABnzbd connections and versions
    for sabnzbd in settings.download_clients.sabnzbd:
        await sabnzbd.setup()

    # Setup arrs (apply checks, and store information)
    settings.instances.check_any_arrs()
    for arr in settings.instances:
        await arr.setup()

    _exit_if_all_failed_definitively(settings)


def _exit_if_all_failed_definitively(settings):
    """Exit only if every configured unit failed with a non-recoverable config error.

    A unit that failed transiently (timeout, connection) keeps the app alive:
    it is retried every cycle and rejoins once its server responds.
    """
    units = _all_units(settings)
    if units and all(
        not unit.ready and unit.failure_kind == "definitive" for unit in units
    ):
        logger.error(
            "All configured instances and download clients failed their startup "
            "checks with configuration errors that cannot self-heal. "
            "Please review the errors above, fix your configuration, and restart.",
        )
        wait_and_exit()


async def retry_degraded_instances(settings, watch_manager=None):
    """Re-attempt setup of degraded units each cycle; report definitive failures."""
    for unit in _all_units(settings):
        if unit.ready:
            continue
        if unit.failure_kind == "definitive":
            logger.error(
                f"SKIP | {_unit_label(unit)}: configuration error - {unit.last_error}. "
                f"Fix configuration and restart. {unit.setup_tip}".rstrip(),
            )
            continue
        if await unit.setup():
            logger.info(
                f"REJOINED | {_unit_label(unit)}: setup succeeded - resuming jobs"
            )
            if (
                watch_manager
                and getattr(unit, "arr_type", None) in ("sonarr", "sportarr", "radarr")
                and settings.jobs.detect_deletions.enabled
            ):
                await watch_manager.setup_for_arr(unit)
        else:
            logger.warning(
                f"SKIP | {_unit_label(unit)}: not reachable - {unit.last_error} "
                f"(will retry next cycle)",
            )

    # A transient unit may have turned definitive on retry (e.g. a slow qBit
    # finally answered, revealing a bad key). Re-evaluate so the app doesn't spin
    # forever with nothing left that can heal.
    _exit_if_all_failed_definitively(settings)
