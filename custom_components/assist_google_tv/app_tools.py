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

from .adb_tv import SHUTDOWN_COMMAND, async_adb_keys, async_adb_output, async_switch_input, normalize_input_name
from .const import CONF_LIVE_TV_INPUT, CONF_TV_APPS, CONF_TV_ENTITY_ID, CONF_TV_METHOD, DOMAIN
from .services import _async_dismiss_screensaver

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
            await _async_dismiss_screensaver(hass, entity_id, method, llm_context.context)
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


class GoogleTVHomeTool(llm.Tool):
    """Send the HOME key to the configured Google TV; related: app launch/stop tools."""

    name = f"{DOMAIN}__go_home"
    title = "Google TV 홈 화면으로 이동"
    integration = DOMAIN
    description = "Return to the Google TV home screen using the HOME key. This does not turn off the TV."
    parameters = schema_api.Schema({})
    if hasattr(llm, "ToolAnnotations"):
        annotations = llm.ToolAnnotations(read_only=False, destructive=False, idempotent=True, open_world=False)

    def __init__(self, entry):
        self._entry = entry

    async def async_call(self, hass, tool_input, llm_context):
        method, entity_id, _apps = _settings(self._entry)
        self.parameters(tool_input.tool_args)
        expected_domain = "remote" if method == "remote" else "media_player"
        if not method or not entity_id.startswith(f"{expected_domain}."):
            raise ServiceValidationError("Google TV app settings are unavailable")
        if llm_context.assistant != "conversation":
            raise ServiceValidationError("Google TV home control is only available to Assist")
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
        service_domain, service_name = (
            ("remote", "send_command") if method == "remote" else ("androidtv", "adb_command")
        )
        if not hass.services.has_service(service_domain, service_name):
            raise ServiceValidationError("Google TV key command service is unavailable")
        service_data = {"entity_id": entity_id, "command": "HOME"}
        try:
            await hass.services.async_call(
                service_domain, service_name, service_data,
                blocking=True, context=llm_context.context,
            )
        except HomeAssistantError:
            raise HomeAssistantError("Google TV home navigation request failed") from None
        except Exception:
            _LOGGER.exception("Google TV home navigation failed for %s", entity_id)
            raise HomeAssistantError("Google TV home navigation request failed") from None
        result = {"status": "home_navigation_requested", "entity_id": entity_id}
        return llm.ToolResult(data=result) if hasattr(llm, "ToolResult") else result


# Add ADB input and power controls; related: adb_tv.py, config_flow.py, and translations/.
class GoogleTVADBTool(llm.Tool):
    integration = DOMAIN
    parameters = schema_api.Schema({})
    if hasattr(llm, "ToolAnnotations"):
        annotations = llm.ToolAnnotations(read_only=False, destructive=False, idempotent=True, open_world=False)

    def __init__(self, entry, lock: asyncio.Lock):
        self._entry = entry
        self._lock = lock

    async def async_call(self, hass, tool_input, llm_context):
        args = self.parameters(tool_input.tool_args)
        settings = {**self._entry.data, **self._entry.options}
        entity_id = settings.get(CONF_TV_ENTITY_ID, "").strip()
        if (llm_context.assistant != "conversation" or settings.get(CONF_TV_METHOD) != "adb"
                or not entity_id.startswith("media_player.")):
            raise ServiceValidationError("This Google TV control requires an ADB target in Assist")
        if not exposed_entities.async_should_expose(hass, "conversation", entity_id):
            raise ServiceValidationError("Google TV entity is not exposed to Assist")
        context = llm_context.context
        if user_id := getattr(context, "user_id", None):
            user = await hass.auth.async_get_user(user_id)
            if user is None or not user.is_active or not user.permissions.check_entity(entity_id, POLICY_CONTROL):
                raise ServiceValidationError("Google TV control is not allowed")
        async with self._lock:
            state = hass.states.get(entity_id)
            if state is None or state.state in ("unknown", "unavailable"):
                raise ServiceValidationError("Google TV entity is unavailable")
            try:
                result = await self._async_execute(hass, entity_id, context, settings, args)
            except ServiceValidationError:
                raise
            except Exception:
                _LOGGER.debug("ADB TV control %s failed for %s", self.name, entity_id, exc_info=True)
                raise HomeAssistantError("The ADB TV action could not be verified") from None
        result["entity_id"] = entity_id
        return llm.ToolResult(data=result) if hasattr(llm, "ToolResult") else result


class GoogleTVInputTool(GoogleTVADBTool):
    name = f"{DOMAIN}__select_input"
    title = "Google TV 입력 전환"
    description = (
        "Select a TV input, such as HDMI 2, AV, or TV. Use live_tv for broadcast TV "
        "requests such as '생방송 틀어 줘' to select the configured broadcast source. "
        "Use TV for the built-in tuner when requested explicitly."
    )
    parameters = schema_api.Schema({schema_api.Required("input"): str})

    async def _async_execute(self, hass, entity_id, context, settings, args):
        requested = args["input"].strip()
        target = settings.get(CONF_LIVE_TV_INPUT, "TV") if requested.casefold() == "live_tv" else requested
        if not isinstance(target, str) or not (target := normalize_input_name(target)):
            raise ServiceValidationError("Choose a supported TV input or configure a broadcast input")
        await async_switch_input(hass, entity_id, target, context)
        return {"status": "input_selected", "input": target}


class GoogleTVTurnOffTool(GoogleTVADBTool):
    name = f"{DOMAIN}__turn_off_tv"
    title = "Google TV 끄기"
    description = "Turn off the TV by putting it into standby. Use for ordinary requests to turn off the TV."

    async def _async_execute(self, hass, entity_id, context, settings, args):
        await async_adb_keys(hass, entity_id, context, "SLEEP")
        return {"status": "standby_requested"}


class GoogleTVShutdownTool(GoogleTVADBTool):
    name = f"{DOMAIN}__shutdown_tv"
    title = "Google TV 완전 종료"
    description = (
        "Shut down the TV system completely. Use only for explicit requests such as "
        "'TV 완전히 꺼 줘' or 'Shut down the TV completely'. The ADB connection will close."
    )
    if hasattr(llm, "ToolAnnotations"):
        annotations = llm.ToolAnnotations(read_only=False, destructive=True, idempotent=True, open_world=False)

    async def _async_execute(self, hass, entity_id, context, settings, args):
        output = await async_adb_output(hass, entity_id, SHUTDOWN_COMMAND, context)
        if output.strip() != "shutdown_scheduled":
            raise ServiceValidationError("Android TV did not accept the shutdown request")
        return {"status": "shutdown_requested"}


class GoogleTVAppsAPI(llm.API):
    """Selectable provider for configured app launching and ADB app stopping."""

    def __init__(self, hass, entry):
        super().__init__(hass=hass, id=f"{DOMAIN}_apps", name="Assist Google TV (App Launch)")
        self._entry = entry
        self._adb_lock = asyncio.Lock()

    async def async_get_api_instance(self, llm_context):
        method, entity_id, apps = _settings(self._entry)
        state = self.hass.states.get(entity_id) if entity_id else None
        tools = []
        prompt = ""
        if llm_context.assistant == "conversation" and state is not None:
            tools = [GoogleTVHomeTool(self._entry)]
            if apps:
                tools.insert(0, GoogleTVAppTool(self._entry))
            if method == "adb" and apps:
                tools.append(GoogleTVStopAppTool(self._entry))
            # Tool descriptions and app enums carry routing rules; related: tests/test_service_only.py.
            prompt = "A successful response confirms only that a request was sent."
            if method == "adb":
                prompt += " Never turn off the TV to close an app."
                tools.extend(tool(self._entry, self._adb_lock) for tool in (
                    GoogleTVInputTool, GoogleTVTurnOffTool, GoogleTVShutdownTool,
                ))
                prompt += (
                    " For ADB, use select_input for an explicit input or live_tv for broadcast. "
                    "Use turn_off_tv for ordinary power-off requests. Use shutdown_tv only for an "
                    "explicit request to shut down completely. Input selection verifies the active input."
                )
        return llm.APIInstance(api=self, api_prompt=prompt, llm_context=llm_context, tools=tools)
