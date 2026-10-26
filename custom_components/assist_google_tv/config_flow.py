"""Configure API credentials, a TV target, allowed apps, and playback; related: const.py, app_tools.py, translations/."""

import json

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er, selector
from homeassistant.helpers.selector import SelectSelectorMode

from .const import (
    CONF_API_KEY,
    CONF_PLAYBACK_MODE,
    CONF_TV_APPS,
    CONF_TV_ENTITY_ID,
    CONF_TV_METHOD,
    DEFAULT_PLAYBACK_MODE,
    DOMAIN,
    PLAYBACK_MODE_APP_LINKS,
    PLAYBACK_MODE_CAST,
    PLAYBACK_MODE_CAST_FALLBACK,
    PLAYBACK_MODE_SMARTTUBE,
    PLAYBACK_MODE_YOUTUBE_APP,
)

CONF_TV_SELECTED_APPS = "tv_selected_apps"
CONF_TV_CUSTOM_APPS = "tv_custom_apps"
_APP_JSON_DEFAULT = '[{"name":"YouTube","launch":"https://www.youtube.com"}]'
_PLAYBACK_OPTIONS = {
    PLAYBACK_MODE_CAST_FALLBACK: "SmartTube → Cast fallback",
    PLAYBACK_MODE_CAST: "Google Cast only",
    PLAYBACK_MODE_YOUTUBE_APP: "Official YouTube app → Cast fallback",
    PLAYBACK_MODE_SMARTTUBE: "SmartTube → Cast fallback",
}
_MEDIA_TERMS = (
    "youtube", "netflix", "prime video", "amazon video", "disney", "spotify",
    "plex", "kodi", "smarttube", "twitch", "hulu", "max", "apple tv",
    "crunchyroll", "tubi", "pluto", "peacock", "paramount", "jellyfin",
    "emby", "stremio", "sling", "discovery", "starz", "espn", "dazn",
    "tving", "coupang play", "wavve", "watcha", "mubi", "fubo", "live tv",
)
_KNOWN_PACKAGES = {
    "com.google.android.youtube.tv": "YouTube",
    "com.google.android.youtube.tvmusic": "YouTube Music",
    "com.netflix.ninja": "Netflix",
    "com.amazon.amazonvideo.livingroom": "Prime Video",
    "com.disney.disneyplus": "Disney+",
    "com.spotify.tv.android": "Spotify",
    "com.plexapp.android": "Plex",
    "org.xbmc.kodi": "Kodi",
    "org.smarttube.stable": "SmartTube",
    "com.google.android.videos": "Google TV",
    "org.jellyfin.androidtv": "Jellyfin",
    "net.cj.em.tving": "TVING",
    "com.coupang.mobile.play": "Coupang Play",
}


def _api_key_field(required: bool):
    marker = vol.Required(CONF_API_KEY) if required else vol.Optional(CONF_API_KEY)
    return marker, selector.TextSelector(
        selector.TextSelectorConfig(
            type=selector.TextSelectorType.PASSWORD,
            autocomplete="new-password",
        )
    )


def _tv_control_schema(defaults: dict | None = None):
    defaults = defaults or {}
    method_key = vol.Required(CONF_TV_METHOD, default=defaults.get(CONF_TV_METHOD, "remote"))
    entity_key = vol.Required(
        CONF_TV_ENTITY_ID,
        **({"default": defaults[CONF_TV_ENTITY_ID]} if defaults.get(CONF_TV_ENTITY_ID) else {}),
    )
    return vol.Schema(
        {
            method_key: selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        {"value": "remote", "label": "Android TV Remote"},
                        {"value": "adb", "label": "Android TV ADB"},
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            entity_key: selector.EntitySelector(
                selector.EntitySelectorConfig(domain=["remote", "media_player"])
            ),
        }
    )


def _app_schema(candidates: list[dict], selected: list[str], custom_apps: str = "[]"):
    return vol.Schema(
        {
            vol.Required(CONF_TV_SELECTED_APPS, default=selected): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        {"value": app["launch"], "label": app["name"]}
                        for app in candidates
                    ],
                    multiple=True,
                    mode=selector.SelectSelectorMode.LIST,
                )
            ),
            vol.Optional(CONF_TV_CUSTOM_APPS, default=custom_apps): selector.TextSelector(
                selector.TextSelectorConfig(multiline=True)
            ),
        }
    )


def _playback_schema(default: str):
    return vol.Schema(
        {
            vol.Required(CONF_PLAYBACK_MODE, default=default): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[{"value": key, "label": label} for key, label in _PLAYBACK_OPTIONS.items()],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            )
        }
    )


def _valid_apps(value):
    """Validate app arrays from JSON; related: app selection flow and app_tools.py."""
    try:
        apps = json.loads(value) if isinstance(value, str) else value
    except (TypeError, ValueError):
        return False
    return (
        isinstance(apps, list)
        and len(apps) <= 30
        and all(
            isinstance(app, dict)
            and isinstance(app.get("name"), str)
            and bool(app["name"].strip())
            and isinstance(app.get("launch"), str)
            and bool(app["launch"].strip())
            for app in apps
        )
        and len({app["name"].strip().casefold() for app in apps}) == len(apps)
    )


def _normalize_apps(apps):
    merged = []
    seen = set()
    for app in apps:
        item = {"name": app["name"].strip(), "launch": app["launch"].strip()}
        key = (item["name"].casefold(), item["launch"])
        if key not in seen:
            merged.append(item)
            seen.add(key)
    return merged


def _selected_apps(candidates: list[dict], selected: list[str] | str, custom_value: str):
    try:
        custom = json.loads(custom_value or "[]")
    except (TypeError, ValueError):
        return None
    if not isinstance(custom, list) or not _valid_apps(custom):
        return None
    selected_values = [selected] if isinstance(selected, str) else selected
    if not isinstance(selected_values, list):
        return None
    chosen = [app for app in candidates if app["launch"] in selected_values]
    apps = _normalize_apps([*chosen, *custom])
    return apps if len(apps) <= 30 and _valid_apps(apps) else None


def _merge_app_lists(*lists: list[dict]):
    merged = _normalize_apps([app for apps in lists for app in apps])
    names = set()
    unique = []
    for app in merged:
        name = app["name"]
        key = name.casefold()
        if key in names:
            name = f"{name} ({app['launch']})"
            key = name.casefold()
            suffix = 2
            while key in names:
                name = f"{app['name']} ({app['launch']}, {suffix})"
                key = name.casefold()
                suffix += 1
        names.add(key)
        unique.append({"name": name, "launch": app["launch"]})
    return unique


def _is_media_app(name: str, launch: str):
    package_id = launch.split("/", 1)[0]
    return package_id in _KNOWN_PACKAGES or any(
        term in f"{name} {launch}".casefold() for term in _MEDIA_TERMS
    )


def _detected_tv_apps(hass, method: str, entity_id: str):
    """Read candidate apps from Remote options or ADB source_list; they may be incomplete."""
    apps = []
    if method == "remote":
        registry_entry = er.async_get(hass).async_get(entity_id)
        config_entry_id = getattr(registry_entry, "config_entry_id", None)
        config_entry = (
            hass.config_entries.async_get_entry(config_entry_id)
            if config_entry_id
            else None
        )
        configured = config_entry.options.get("apps", {}) if config_entry else {}
        if isinstance(configured, dict):
            for app_id, app in configured.items():
                if isinstance(app_id, str) and isinstance(app, dict):
                    apps.append({
                        "name": str(app.get("app_name") or _KNOWN_PACKAGES.get(app_id, app_id)).strip(),
                        "launch": app_id,
                    })
    else:
        state = hass.states.get(entity_id)
        sources = state.attributes.get("source_list", []) if state else []
        if isinstance(sources, list):
            apps.extend(
                {"name": source.strip(), "launch": source.strip()}
                for source in sources
                if isinstance(source, str) and source.strip()
            )
    candidates = []
    for app in apps:
        launch = app["launch"].split("/", 1)[0] if "/" in app["launch"] and not app["launch"].startswith(("http://", "https://")) else app["launch"]
        name = _KNOWN_PACKAGES.get(launch, app["name"])
        if _is_media_app(name, launch):
            candidates.append({"name": name, "launch": launch})
    return _merge_app_lists(candidates)


async def _adb_tv_launchers(hass, entity_id: str):
    """Query launchable media packages; related: ADB app candidate selection."""
    if not hass.services.has_service("androidtv", "adb_command"):
        return []
    try:
        response = await hass.services.async_call(
            "androidtv",
            "adb_command",
            {
                "entity_id": entity_id,
                "command": "cmd package query-activities --brief -a android.intent.action.MAIN -c android.intent.category.LEANBACK_LAUNCHER",
            },
            blocking=True,
            return_response=True,
        )
    except Exception:
        return []
    if not isinstance(response, dict):
        return []
    output = response.get("adb_response")
    if not isinstance(output, str):
        output = next(
            (
                item.get("adb_response")
                for item in response.values()
                if isinstance(item, dict) and isinstance(item.get("adb_response"), str)
            ),
            "",
        )
    apps = []
    for line in output.splitlines() if isinstance(output, str) else []:
        component = line.strip().split()[0] if line.strip() else ""
        package_id, separator, _activity = component.partition("/")
        if not separator or not package_id:
            continue
        name = _KNOWN_PACKAGES.get(package_id, package_id)
        if _is_media_app(name, package_id):
            apps.append({"name": name, "launch": package_id})
    return _merge_app_lists(apps)


class YouTubeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        errors = {}
        if user_input is not None:
            api_key = user_input.get(CONF_API_KEY, "").strip()
            if api_key:
                self._flow_data = {CONF_API_KEY: api_key}
                return await self.async_step_tv_control()
            errors["base"] = "api_key_required"
        api_key_key, api_key_selector = _api_key_field(True)
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({api_key_key: api_key_selector}),
            errors=errors,
        )

    async def async_step_tv_control(self, user_input=None):
        errors = {}
        defaults = getattr(self, "_flow_data", {})
        if user_input is not None:
            method = user_input[CONF_TV_METHOD]
            entity_id = user_input[CONF_TV_ENTITY_ID]
            valid_domain = (
                (method == "remote" and entity_id.startswith("remote."))
                or (method == "adb" and entity_id.startswith("media_player."))
            )
            state = self.hass.states.get(entity_id)
            if not valid_domain or state is None:
                errors["base"] = "tv_entity_not_found"
            else:
                defaults.update({CONF_TV_METHOD: method, CONF_TV_ENTITY_ID: entity_id})
                self._flow_data = defaults
                detected = _detected_tv_apps(self.hass, method, entity_id)
                if method == "adb":
                    detected = _merge_app_lists(
                        await _adb_tv_launchers(self.hass, entity_id), detected
                    )
                existing = _apps_from_settings(defaults) if CONF_TV_APPS in defaults else []
                self._app_candidates = _merge_app_lists(detected, existing) or _default_apps()
                return await self.async_step_apps()
        return self.async_show_form(
            step_id="tv_control", data_schema=_tv_control_schema(defaults), errors=errors
        )

    async def async_step_apps(self, user_input=None):
        candidates = getattr(self, "_app_candidates", _default_apps())
        defaults = getattr(self, "_flow_data", {})
        existing_apps = _apps_from_settings(defaults) if CONF_TV_APPS in defaults else []
        default_selected = (
            [app["launch"] for app in existing_apps]
            if CONF_TV_APPS in defaults
            else [app["launch"] for app in candidates]
        )
        errors = {}
        if user_input is not None:
            apps = _selected_apps(
                candidates,
                user_input.get(CONF_TV_SELECTED_APPS, []),
                user_input.get(CONF_TV_CUSTOM_APPS, "[]"),
            )
            if apps is None:
                errors[CONF_TV_CUSTOM_APPS] = "invalid_apps"
            else:
                defaults[CONF_TV_APPS] = json.dumps(apps, ensure_ascii=False)
                self._flow_data = defaults
                return await self.async_step_playback_mode()
        return self.async_show_form(
            step_id="apps",
            data_schema=_app_schema(
                candidates,
                user_input.get(CONF_TV_SELECTED_APPS, default_selected) if user_input else default_selected,
                user_input.get(CONF_TV_CUSTOM_APPS, "[]") if user_input else "[]",
            ),
            errors=errors,
        )

    async def async_step_playback_mode(self, user_input=None):
        defaults = getattr(self, "_flow_data", {})
        if user_input is not None:
            defaults[CONF_PLAYBACK_MODE] = _normalize_playback_mode(user_input[CONF_PLAYBACK_MODE])
            return self.async_create_entry(title="Assist Google TV", data=defaults)
        return self.async_show_form(
            step_id="playback_mode",
            data_schema=_playback_schema(defaults.get(CONF_PLAYBACK_MODE, DEFAULT_PLAYBACK_MODE)),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return YouTubeOptionsFlowHandler(config_entry)


class YouTubeOptionsFlowHandler(config_entries.OptionsFlow):
    """Reconfigure the entry using the same ordered steps; related: config flow above."""

    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        super().__init__()
        self._entry = entry
        self._flow_data = {**entry.data, **entry.options}

    async def async_step_init(self, user_input=None):
        errors = {}
        if user_input is not None:
            new_key = user_input.get(CONF_API_KEY, "").strip()
            api_key = new_key or self._flow_data.get(CONF_API_KEY, "")
            if api_key:
                self._flow_data[CONF_API_KEY] = api_key
                return await self.async_step_tv_control()
            errors["base"] = "api_key_required"
        api_key_key, api_key_selector = _api_key_field(False)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({api_key_key: api_key_selector}),
            errors=errors,
        )

    async def async_step_tv_control(self, user_input=None):
        errors = {}
        if user_input is not None:
            method = user_input[CONF_TV_METHOD]
            entity_id = user_input[CONF_TV_ENTITY_ID]
            valid_domain = (
                (method == "remote" and entity_id.startswith("remote."))
                or (method == "adb" and entity_id.startswith("media_player."))
            )
            if not valid_domain or self.hass.states.get(entity_id) is None:
                errors["base"] = "tv_entity_not_found"
            else:
                self._flow_data.update({CONF_TV_METHOD: method, CONF_TV_ENTITY_ID: entity_id})
                detected = _detected_tv_apps(self.hass, method, entity_id)
                if method == "adb":
                    detected = _merge_app_lists(
                        await _adb_tv_launchers(self.hass, entity_id), detected
                    )
                existing = (
                    _apps_from_settings(self._flow_data)
                    if CONF_TV_APPS in self._flow_data
                    else []
                )
                self._app_candidates = _merge_app_lists(detected, existing) or _default_apps()
                return await self.async_step_apps()
        return self.async_show_form(
            step_id="tv_control",
            data_schema=_tv_control_schema(self._flow_data),
            errors=errors,
        )

    async def async_step_apps(self, user_input=None):
        candidates = getattr(self, "_app_candidates", _default_apps())
        existing_apps = (
            _apps_from_settings(self._flow_data)
            if CONF_TV_APPS in self._flow_data
            else []
        )
        default_selected = (
            [app["launch"] for app in existing_apps]
            if CONF_TV_APPS in self._flow_data
            else [app["launch"] for app in candidates]
        )
        errors = {}
        if user_input is not None:
            apps = _selected_apps(
                candidates,
                user_input.get(CONF_TV_SELECTED_APPS, []),
                user_input.get(CONF_TV_CUSTOM_APPS, "[]"),
            )
            if apps is None:
                errors[CONF_TV_CUSTOM_APPS] = "invalid_apps"
            else:
                self._flow_data[CONF_TV_APPS] = json.dumps(apps, ensure_ascii=False)
                return await self.async_step_playback_mode()
        return self.async_show_form(
            step_id="apps",
            data_schema=_app_schema(
                candidates,
                user_input.get(CONF_TV_SELECTED_APPS, default_selected) if user_input else default_selected,
                user_input.get(CONF_TV_CUSTOM_APPS, "[]") if user_input else "[]",
            ),
            errors=errors,
        )

    async def async_step_playback_mode(self, user_input=None):
        if user_input is not None:
            self._flow_data[CONF_PLAYBACK_MODE] = _normalize_playback_mode(
                user_input[CONF_PLAYBACK_MODE]
            )
            return self.async_create_entry(title="", data=self._flow_data)
        return self.async_show_form(
            step_id="playback_mode",
            data_schema=_playback_schema(
                self._flow_data.get(CONF_PLAYBACK_MODE, DEFAULT_PLAYBACK_MODE)
            ),
        )


def _default_apps():
    return json.loads(_APP_JSON_DEFAULT)


def _apps_from_settings(settings: dict):
    value = settings.get(CONF_TV_APPS, _APP_JSON_DEFAULT)
    try:
        apps = json.loads(value) if isinstance(value, str) else value
    except (TypeError, ValueError):
        return []
    return _normalize_apps(apps) if _valid_apps(apps) else []


def _normalize_playback_mode(value: str):
    valid_modes = {PLAYBACK_MODE_CAST, *PLAYBACK_MODE_APP_LINKS, PLAYBACK_MODE_CAST_FALLBACK}
    return value if value in valid_modes else DEFAULT_PLAYBACK_MODE
