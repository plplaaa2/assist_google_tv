"""Launch configured Google TV apps; related: llm.py, config_flow.py, translations, and README files."""

import asyncio
import json
import logging

import voluptuous as vol

from homeassistant.auth.permissions.const import POLICY_CONTROL
from homeassistant.components.homeassistant import exposed_entities
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import llm

from .const import CONF_TV_APPS, CONF_TV_ENTITY_ID, CONF_TV_METHOD, DOMAIN

try:
    import probatio as schema_api
except ImportError:
    schema_api = vol

_LOGGER = logging.getLogger(__name__)
DEFAULT_TV_APPS = '[{"name":"YouTube","launch":"https://www.youtube.com"}]'


def _settings(entry):
    values = {**entry.data, **entry.options}
    method = values.get(CONF_TV_METHOD, "remote")
    entity_id = values.get(CONF_TV_ENTITY_ID, "").strip()
    try:
        apps = json.loads(values.get(CONF_TV_APPS, DEFAULT_TV_APPS))
    except (TypeError, ValueError):
        return None, None, []
    if method not in ("remote", "adb") or not entity_id or not isinstance(apps, list):
        return None, None, []
    valid = [
        app for app in apps
        if isinstance(app, dict)
        and isinstance(app.get("name"), str) and app["name"].strip()
        and isinstance(app.get("launch"), str) and app["launch"].strip()
    ]
    return method, entity_id, valid


class GoogleTVAppTool(llm.Tool):
    """Open one configured app on the selected TV."""

    name = f"{DOMAIN}__open_app"
    title = "Google TV 앱 실행"
    integration = DOMAIN
    description = "Open one configured app on Google TV. This only launches the app; it does not search or play a title."
    if hasattr(llm, "ToolAnnotations"):
        annotations = llm.ToolAnnotations(read_only=False, destructive=False, idempotent=True, open_world=False)

    def __init__(self, entry):
        self._entry = entry
        _, _, apps = _settings(entry)
        self._apps = {app["name"].strip(): app for app in apps}
        self.parameters = schema_api.Schema(
            {schema_api.Required("app_name"): schema_api.In(sorted(self._apps))}
        )

    async def async_call(self, hass: HomeAssistant, tool_input, llm_context):
        args = self.parameters(tool_input.tool_args)
        method, entity_id, apps = _settings(self._entry)
        app = self._apps.get(args["app_name"])
        if not method or not app or app not in apps:
            raise ServiceValidationError("Google TV app settings are unavailable")
        expected_domain = "remote" if method == "remote" else "media_player"
        if llm_context.assistant != "conversation" or not entity_id.startswith(f"{expected_domain}."):
            raise ServiceValidationError("Choose the configured Google TV entity")
        state = hass.states.get(entity_id)
        if state is None or state.state in ("unknown", "unavailable"):
            raise ServiceValidationError("Google TV entity is unavailable")
        if not exposed_entities.async_should_expose(hass, "conversation", entity_id):
            raise ServiceValidationError("Google TV entity is not exposed to Assist")
        user_id = getattr(llm_context.context, "user_id", None)
        if user_id:
            user = await hass.auth.async_get_user(user_id)
            if user is None or not user.is_active or not user.permissions.check_entity(entity_id, POLICY_CONTROL):
                raise ServiceValidationError("Google TV control is not allowed")
        try:
            if method == "remote":
                if not hass.services.has_service("remote", "turn_on"):
                    raise ServiceValidationError("Android TV Remote service is unavailable")
                await hass.services.async_call(
                    "remote", "turn_on", {"entity_id": entity_id, "activity": app["launch"]},
                    blocking=True, context=llm_context.context,
                )
            else:
                source = app["launch"]
                if not isinstance(source, str) or not source or source.startswith("!"):
                    raise ServiceValidationError("Invalid Google TV app launch value")
                if not hass.services.has_service("media_player", "select_source"):
                    raise ServiceValidationError("Android TV ADB service is unavailable")
                available = state.attributes.get("source_list")
                if isinstance(available, list) and available and source not in available:
                    raise ServiceValidationError("Configured app is not listed by the TV")
                if not hass.services.has_service("androidtv", "adb_command"):
                    raise ServiceValidationError("Android TV ADB service is unavailable")
                await hass.services.async_call(
                    "androidtv", "adb_command", {"entity_id": entity_id, "command": "WAKEUP"},
                    blocking=True, context=llm_context.context,
                )
                await asyncio.sleep(0.5)
                await hass.services.async_call(
                    "media_player", "select_source", {"entity_id": entity_id, "source": source},
                    blocking=True, context=llm_context.context,
                )
        except ServiceValidationError:
            raise
        except HomeAssistantError:
            raise HomeAssistantError("Google TV app launch request failed") from None
        except Exception:
            _LOGGER.exception("Google TV app launch failed for %s", entity_id)
            raise HomeAssistantError("Google TV app launch request failed") from None
        result = llm.ToolResult(data={"status": "app_launch_requested", "app_name": app["name"], "entity_id": entity_id}) if hasattr(llm, "ToolResult") else {"status": "app_launch_requested", "app_name": app["name"], "entity_id": entity_id}
        return result


class GoogleTVStopAppTool(GoogleTVAppTool):
    """Stop a configured app through Android TV ADB without powering off the TV."""

    name = f"{DOMAIN}__stop_app"
    title = "Google TV 앱 종료"
    description = "Stop one configured app using Android TV ADB. This does not turn off the TV."
    if hasattr(llm, "ToolAnnotations"):
        annotations = llm.ToolAnnotations(read_only=False, destructive=False, idempotent=True, open_world=False)

    def __init__(self, entry):
        super().__init__(entry)
        _, _, apps = _settings(entry)
        self._apps = {app["name"].strip(): app for app in apps}

    async def async_call(self, hass, tool_input, llm_context):
        method, entity_id, apps = _settings(self._entry)
        if method != "adb":
            raise ServiceValidationError("Stopping apps is available only with Android TV ADB")
        if llm_context.assistant != "conversation" or not entity_id.startswith("media_player."):
            raise ServiceValidationError("Choose the configured Google TV entity")
        args = self.parameters(tool_input.tool_args)
        app = self._apps.get(args["app_name"])
        if not app or app not in apps:
            raise ServiceValidationError("Google TV app settings are unavailable")
        state = hass.states.get(entity_id)
        if state is None or state.state in ("unknown", "unavailable"):
            raise ServiceValidationError("Google TV entity is unavailable")
        if not exposed_entities.async_should_expose(hass, "conversation", entity_id):
            raise ServiceValidationError("Google TV entity is not exposed to Assist")
        user_id = getattr(llm_context.context, "user_id", None)
        if user_id:
            user = await hass.auth.async_get_user(user_id)
            if user is None or not user.is_active or not user.permissions.check_entity(entity_id, POLICY_CONTROL):
                raise ServiceValidationError("Google TV control is not allowed")
        if not hass.services.has_service("media_player", "select_source"):
            raise ServiceValidationError("Android TV ADB service is unavailable")
        source = app["launch"]
        if not isinstance(source, str) or not source or source.startswith("!"):
            raise ServiceValidationError("Invalid Google TV app launch value")
        try:
            await hass.services.async_call(
                "media_player", "select_source", {"entity_id": entity_id, "source": f"!{source}"},
                blocking=True, context=llm_context.context,
            )
        except HomeAssistantError:
            raise HomeAssistantError("Google TV app stop request failed") from None
        except Exception:
            _LOGGER.exception("Google TV app stop failed for %s", entity_id)
            raise HomeAssistantError("Google TV app stop request failed") from None
        result = {"status": "app_stop_requested", "app_name": app["name"], "entity_id": entity_id}
        return llm.ToolResult(data=result) if hasattr(llm, "ToolResult") else result


class GoogleTVAppsAPI(llm.API):
    """Selectable provider for configured app launching and ADB app stopping."""

    def __init__(self, hass, entry):
        super().__init__(hass=hass, id=f"{DOMAIN}_apps", name="Assist Google TV (App Launch)")
        self._entry = entry

    async def async_get_api_instance(self, llm_context):
        method, entity_id, apps = _settings(self._entry)
        state = self.hass.states.get(entity_id) if entity_id else None
        tools = []
        prompt = ""
        if llm_context.assistant == "conversation" and state is not None and apps:
            tools = [GoogleTVAppTool(self._entry)]
            if method == "adb":
                tools.append(GoogleTVStopAppTool(self._entry))
            prompt = (
                "Use the configured app tool only to open an app. Use the stop tool only when available; "
                "never turn off the TV to close an app. This does not search for or play specific content. "
                "Use exact configured app names. A successful response confirms only that a request was sent. "
                "Configured apps: " + json.dumps([{"name": app["name"], "launch": app["launch"]} for app in apps], ensure_ascii=False)
            )
        return llm.APIInstance(api=self, api_prompt=prompt, llm_context=llm_context, tools=tools)
