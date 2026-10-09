"""YouTube Content Search - 메인 설정 진입점."""
import logging
import os
from homeassistant.components.panel_custom import async_register_panel
from homeassistant.components.frontend import async_remove_panel as frontend_remove_panel
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migration handler for old storage format."""
    if DOMAIN in hass.data:
        del hass.data[DOMAIN]

    hass.data.setdefault(DOMAIN, {})

    if config_entry and hasattr(config_entry, "options") and config_entry.options.get(CONF_API_KEY):
        hass.data[DOMAIN][CONF_API_KEY] = str(config_entry.options.get(CONF_API_KEY))

    return True


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """YouTube Content Search setting entry installation."""

    _LOGGER.info("Setting up %s", DOMAIN)

    hass.data.setdefault(DOMAIN, {})

    # Forward setup to all platforms (none defined for this integration).
    try:
        await hass.config_entries.async_forward_entry_setups(config_entry, [])
    except Exception as err:
        _LOGGER.error("YouTube Content Search forward_entry_setups failed: %s", err, exc_info=True)

    # Register HTTP routes for REST API (web UI backend).
    try:
        from .services import (
            async_handle_youtube_search,
            async_handle_playlist_detail,
            async_handle_playlist_save,
            async_handle_playlist_delete,
        )

        hass.http.app.router.add_route("POST", "/youtube-search", async_handle_youtube_search)
        hass.http.app.router.add_route("GET", "/playlist-detail/{id}", async_handle_playlist_detail)
        hass.http.app.router.add_route("POST", "/playlist-save", async_handle_playlist_save)
        hass.http.app.router.add_route("DELETE", "/playlist-delete/{id}", async_handle_playlist_delete)

    except Exception as err:
        _LOGGER.error("YouTube Content Search HTTP route setup failed: %s", err, exc_info=True)

    # Register HA services (Cast playback / legacy mode).
    try:
        from .services import async_setup_services
        await async_setup_services(hass)
    except Exception as err:
        _LOGGER.error("YouTube Content Search services setup failed: %s", err, exc_info=True)

    # Register custom panel (sidebar Web UI).
    try:
        await hass.http.async_register_static_paths([
            StaticPathConfig(
                url_path="/youtube_content_search",
                path=os.path.join(os.path.dirname(__file__), "frontend"),
                cache_headers=False,
            ),
        ])

        # Register custom panel in sidebar (icon + web UI) — direct API call.
        hass.components.frontend.async_introduce_custom_panel(
            frontend_url_path=PANEL_URL,          # "youtube-content-search" (.html 없음) ✅
            js_url="/youtube_content_search/panel.html",  # fetch로 동적 로드됨 ✅
            sidebar_title=PANEL_TITLE,           # "YouTube Content Search"
            sidebar_icon=PANEL_ICON,             # "mdi:youtube-tv"
        )
        _LOGGER.info("YouTube Content Search panel registered")

    except Exception as err:
        _LOGGER.error("YouTube Content Search panel registration failed: %s", err, exc_info=True)

    return True


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    # Clean up service registration.
    try:
        hass.services.async_remove(DOMAIN, "search_play")
        hass.services.async_remove(DOMAIN, "playlist_save")
        hass.services.async_remove(DOMAIN, "playlist_delete")
    except Exception as err:
        _LOGGER.error("YouTube Content Search services unload failed: %s", err, exc_info=True)

    # Clean up domain data.
    if DOMAIN in hass.data:
        hass.data.pop(DOMAIN, None)

    # Remove custom panel registration.
    try:
        frontend_remove_panel(hass, PANEL_URL)
    except Exception as err:
        _LOGGER.error("YouTube Content Search panel removal failed: %s", err, exc_info=True)

    return True


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """YouTube Content Search initial setup (optional)."""
    try:
        hass.data.setdefault(DOMAIN, {})
    except Exception as err:
        _LOGGER.warning("Storage initialization during startup skipped: %s", err, exc_info=True)

    return True


DOMAIN = "youtube_content_search"
CONF_API_KEY = "api_key"
PANEL_ICON = "mdi:youtube-tv"
PANEL_TITLE = "YouTube Content Search"
PANEL_URL = "youtube-content-search"
