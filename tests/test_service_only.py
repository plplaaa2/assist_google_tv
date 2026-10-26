"""Contract tests with HA doubles; related: config_flow.py, __init__.py, services.py."""
import asyncio
from dataclasses import dataclass
from enum import Enum
import importlib
import json
from pathlib import Path
import re
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, call, patch
import uuid

import aiohttp
import voluptuous as vol

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class HAError(Exception):
    pass


class SupportsResponse(Enum):
    OPTIONAL = "optional"
    ONLY = "only"


class Flow:
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__()

    def _async_current_entries(self):
        return []

    def async_create_entry(self, **kwargs):
        return {"type": "create_entry", **kwargs}

    def async_show_form(self, **kwargs):
        return {"type": "form", **kwargs}

    def async_abort(self, **kwargs):
        return {"type": "abort", **kwargs}


def entity_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9_]+\.[a-z0-9_]+", value):
        raise vol.Invalid("Invalid entity ID")
    return value


# File-backed Store double verifies restart semantics; related: playlist_store.py.
class FileStore:
    def __init__(self, hass, version, key, **kwargs):
        self.path = Path(hass.storage_dir) / key

    async def async_load(self):
        await asyncio.sleep(0)
        return json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else None

    async def async_save(self, data):
        await asyncio.sleep(0)
        pending = self.path.with_suffix(".tmp")
        pending.write_text(json.dumps(data), encoding="utf-8")
        pending.replace(self.path)


# Stub only HA interfaces; aiohttp and voluptuous remain real dependencies.
@dataclass
class LLMTools:
    tools: list
    prompt: str = ""


@dataclass
class LLMResult:
    data: dict
    error: bool = False


class LLMApi:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class SelectorStub:
    def __init__(self, config=None):
        self.config = config

    def __call__(self, value):
        return value


class SelectorMode(Enum):
    DROPDOWN = "dropdown"
    LIST = "list"


modules = {
    "homeassistant": {},
    "homeassistant.core": {"HomeAssistant": object, "ServiceCall": object, "SupportsResponse": SupportsResponse, "callback": lambda f: f},
    "homeassistant.config_entries": {"ConfigEntry": object, "ConfigFlow": Flow, "OptionsFlow": Flow},
    "homeassistant.exceptions": {"HomeAssistantError": HAError, "ServiceValidationError": HAError, "ConfigEntryError": HAError},
    "homeassistant.helpers": {},
    "homeassistant.helpers.config_validation": {"string": vol.All(str), "entity_id": entity_id},
    "homeassistant.helpers.aiohttp_client": {"async_get_clientsession": lambda hass: hass.session},
    "homeassistant.helpers.storage": {"Store": FileStore},
    "homeassistant.helpers.entity_registry": {"async_get": lambda hass: hass.entity_registry},
    "homeassistant.helpers.selector": {
        "SelectSelectorMode": SelectorMode,
        "SelectSelector": SelectorStub,
        "SelectSelectorConfig": lambda **kwargs: kwargs,
        "TextSelector": SelectorStub,
        "TextSelectorType": SimpleNamespace(PASSWORD="password"),
        "TextSelectorConfig": lambda **kwargs: kwargs,
        "EntitySelector": SelectorStub,
        "EntitySelectorConfig": lambda **kwargs: kwargs,
    },
    "homeassistant.components": {},
    "homeassistant.components.llm": {"LLMTools": LLMTools},
    "homeassistant.components.homeassistant": {},
    "homeassistant.components.homeassistant.exposed_entities": {
        "async_should_expose": lambda hass, assistant, entity: entity in hass.exposed,
    },
    "homeassistant.auth": {},
    "homeassistant.auth.permissions": {},
    "homeassistant.auth.permissions.const": {"POLICY_CONTROL": "control"},
    "homeassistant.helpers.llm": {
        "Tool": object, "API": LLMApi, "APIInstance": LLMApi,
        "LLM_API_ASSIST": "assist", "ToolResult": LLMResult,
        "async_register_api": Mock(return_value=Mock()),
    },
}
for name, attributes in modules.items():
    module = ModuleType(name)
    module.__dict__.update(attributes)
    module.__path__ = []
    sys.modules[name] = module
sys.modules["homeassistant.helpers"].entity_registry = sys.modules["homeassistant.helpers.entity_registry"]
sys.modules["homeassistant.helpers"].selector = sys.modules["homeassistant.helpers.selector"]

integration = importlib.import_module("custom_components.assist_google_tv")
services = importlib.import_module("custom_components.assist_google_tv.services")
flows = importlib.import_module("custom_components.assist_google_tv.config_flow")
llm_tools = importlib.import_module("custom_components.assist_google_tv.llm")
playlist_store = importlib.import_module("custom_components.assist_google_tv.playlist_store")


class Registry:
    def __init__(self):
        self.actions = {}
        self.async_call = AsyncMock()

    def has_service(self, domain, name):
        return (domain == "assist_google_tv" and name in self.actions) or domain in {
            "remote", "media_player", "androidtv",
        }

    def async_register(self, domain, name, handler, schema, **kwargs):
        self.actions[name] = (handler, schema, kwargs.get("supports_response"))

    async def invoke(self, name, data):
        handler, schema, _supports_response = self.actions[name]
        return await handler(SimpleNamespace(data=schema(data)))


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    def test_manifest_domain_matches_integration_folder(self):
        manifest = json.loads((ROOT / "custom_components/assist_google_tv/manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["domain"], "assist_google_tv")

    async def asyncSetUp(self):
        self.storage_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.storage_dir.cleanup)
        self.states = {}
        self.entity_entries = {
            "media_player.tv": SimpleNamespace(platform="cast"),
            "remote.tv": SimpleNamespace(platform="androidtv_remote"),
        }
        self.hass = SimpleNamespace(data={}, storage_dir=self.storage_dir.name, services=Registry(), states=SimpleNamespace(
            get=self.states.get,
            async_all=lambda: list(self.states.values()),
            async_set=lambda name, state, attrs: self.states.update({name: SimpleNamespace(entity_id=name, attributes=attrs)}),
            async_remove=lambda name: self.states.pop(name, None),
        ))
        self.hass.entity_registry = SimpleNamespace(async_get=self.entity_entries.get)
        self.entry = SimpleNamespace(data={"api_key": uuid.uuid4().hex}, options={},
            async_on_unload=Mock(), add_update_listener=Mock())
        await integration.async_setup(self.hass, {})
        await integration.async_setup_entry(self.hass, self.entry)

    # Verify discovery, authorization and fallback contracts; related: llm.py.
    def _llm_context(self):
        self.hass.exposed = {"media_player.tv"}
        self.states["media_player.tv"] = SimpleNamespace(
            entity_id="media_player.tv", state="idle", attributes={"friendly_name": "Living room TV"},
        )
        return SimpleNamespace(assistant="conversation", context=object())

    async def test_cast_filter_excludes_other_and_unregistered_players(self):
        context = self._llm_context()
        for entity, platform in [("media_player.tv_remote", "androidtv_remote"),
                                 ("media_player.speaker", "sonos"),
                                 ("media_player.unregistered", None)]:
            self.states[entity] = SimpleNamespace(entity_id=entity, state="idle", attributes={})
            self.hass.exposed.add(entity)
            if platform:
                self.entity_entries[entity] = SimpleNamespace(platform=platform)
        result = await llm_tools.YouTubeAPI(self.hass).async_get_api_instance(context)
        for entity in ["media_player.tv_remote", "media_player.speaker", "media_player.unregistered"]:
            self.assertNotIn(entity, result.api_prompt)
            with self.assertRaises(HAError):
                await result.tools[0].async_call(
                    self.hass, SimpleNamespace(tool_args={"query": "music", "entity_id": entity}), context,
                )
            with patch.object(services, "_async_youtube_request", AsyncMock()) as request:
                with self.assertRaises(HAError):
                    await self.hass.services.invoke("youtube_search_play", {"query": "music", "entity_id": entity})
                request.assert_not_awaited()
        self.hass.services.async_call.assert_not_awaited()

    async def test_cast_identity_rechecked_at_call_time(self):
        context = self._llm_context()
        tool = (await llm_tools.YouTubeAPI(self.hass).async_get_api_instance(context)).tools[0]
        self.entity_entries["media_player.tv"].platform = "androidtv_remote"
        self.assertEqual((await llm_tools.YouTubeAPI(self.hass).async_get_api_instance(context)).tools, [])
        with self.assertRaises(HAError):
            await tool.async_call(self.hass, SimpleNamespace(tool_args={"query": "music", "entity_id": "media_player.tv"}), context)
        self.hass.services.async_call.assert_not_awaited()

    async def test_assist_tool_discovery_and_playback_context(self):
        context = self._llm_context()
        result = await llm_tools.YouTubeAPI(self.hass).async_get_api_instance(context)
        self.assertEqual(len(result.tools), 1)
        self.assertIn("media_player.tv", result.api_prompt)
        self.assertNotIn(self.entry.data["api_key"], result.api_prompt)
        args = {"query": "music", "entity_id": "media_player.tv", "cast_entity_id": "media_player.tv"}
        response = await result.tools[0].async_call(self.hass, SimpleNamespace(tool_args=args), context)
        self.assertEqual(response.data["status"], "playback_requested")
        self.hass.services.async_call.assert_awaited_once_with(
            "assist_google_tv", "youtube_search_play", args, blocking=True, context=context.context,
        )
        self.assertEqual(result.tools[0].name, "assist_google_tv__youtube_search_play")
        self.assertIsNone(llm_tools.async_get_tools(self.hass, context, "other_api"))
        self.assertIsNone(llm_tools.async_get_tools(self.hass, context, "assist"))

    async def test_assist_tool_rechecks_exposure_and_configuration(self):
        context = self._llm_context()
        tool = (await llm_tools.YouTubeAPI(self.hass).async_get_api_instance(context)).tools[0]
        call = SimpleNamespace(tool_args={"query": "music", "entity_id": "media_player.tv", "cast_entity_id": "media_player.tv"})
        self.hass.exposed.clear()
        self.assertEqual(len((await llm_tools.YouTubeAPI(self.hass).async_get_api_instance(context)).tools), 1)
        self.states["media_player.tv"].state = "unavailable"
        response = await tool.async_call(self.hass, call, context)
        self.assertEqual(response.data["status"], "playback_requested")
        self.states["media_player.tv"].state = "idle"
        context.assistant = "cloud.alexa"
        with self.assertRaises(HAError):
            await tool.async_call(self.hass, call, context)
        context.assistant = "conversation"
        call.tool_args["query"] = " "
        with self.assertRaises(HAError):
            await tool.async_call(self.hass, call, context)
        self.hass.services.async_call.reset_mock()
        context.assistant = "conversation"
        await integration.async_unload_entry(self.hass, self.entry)
        self.assertEqual((await llm_tools.YouTubeAPI(self.hass).async_get_api_instance(context)).tools, [])
        with self.assertRaises(HAError):
            await tool.async_call(self.hass, call, context)
        self.hass.services.async_call.assert_not_awaited()

    async def test_assist_errors_do_not_forward_backend_text(self):
        context = self._llm_context()
        self.hass.services.async_call.side_effect = HAError("private backend diagnostic")
        with self.assertRaisesRegex(HAError, "^YouTube search or playback request failed$"):
            await llm_tools.YouTubeSearchPlayTool().async_call(
                self.hass, SimpleNamespace(tool_args={"query": "music", "entity_id": "media_player.tv", "cast_entity_id": "media_player.tv"}), context,
            )

    # Exercise setup, API listing and unload instead of just mocking registration.
    async def test_provider_list_registration_unload_and_reload(self):
        providers = {}
        callbacks = []

        def register(hass, api):
            if api.id in providers:
                raise HAError("Duplicate API")
            providers[api.id] = api
            return lambda: providers.pop(api.id)

        self.entry.async_on_unload = callbacks.append
        with patch.object(llm_tools.llm, "async_register_api", register):
            await integration.async_setup_entry(self.hass, self.entry)
            self.assertEqual(providers["assist_google_tv"].name, "Assist Google TV (YouTube)")
            self.assertEqual(providers["assist_google_tv_netflix"].name, "Assist Google TV (Netflix)")
            await integration._async_update_options(self.hass, self.entry)
            self.assertEqual(len(providers), 3)
            await integration.async_unload_entry(self.hass, self.entry)
            for cleanup in callbacks:
                cleanup()
            self.assertEqual(providers, {})
            callbacks.clear()
            # Registration also works without the newer native LLM platform.
            with patch.dict(sys.modules["homeassistant.components.llm"].__dict__, clear=True):
                await integration.async_setup_entry(self.hass, self.entry)
                self.assertIn("assist_google_tv", providers)
                for cleanup in callbacks:
                    cleanup()
                self.assertEqual(providers, {})

    async def test_provider_api_registration_and_legacy_result(self):
        context = self._llm_context()
        register = sys.modules["homeassistant.helpers.llm"].async_register_api
        register.reset_mock()
        with patch.object(llm_tools.llm, "async_register_api", register):
            llm_tools.async_register_api(self.hass, self.entry)
            self.assertEqual(register.call_count, 3)
            apis = [call.args[1] for call in register.call_args_list]
            self.assertEqual([api.id for api in apis], ["assist_google_tv", "assist_google_tv_netflix", "assist_google_tv_apps"])
            self.entry.async_on_unload.assert_any_call(register.return_value)
            api = apis[0]
            instance = await api.async_get_api_instance(context)
            self.assertEqual(len(instance.tools), 1)
            self.assertEqual(api.id, "assist_google_tv")
            with patch.dict(sys.modules["homeassistant.helpers.llm"].__dict__):
                del sys.modules["homeassistant.helpers.llm"].ToolResult
                result = await instance.tools[0].async_call(
                    self.hass, SimpleNamespace(tool_args={"query": "music", "entity_id": "media_player.tv", "cast_entity_id": "media_player.tv"}), context,
                )
                self.assertEqual(result["status"], "playback_requested")

    async def test_google_tv_app_launch_provider_uses_configured_allowlist(self):
        context = self._llm_context()
        self.entry.options.update({
            "tv_method": "remote",
            "tv_entity_id": "remote.tv",
            "tv_apps": '[{"name":"YouTube","launch":"https://www.youtube.com"}]',
        })
        self.hass.exposed.add("remote.tv")
        self.states["remote.tv"] = SimpleNamespace(
            entity_id="remote.tv", state="on", attributes={"friendly_name": "Living room TV"},
        )
        from custom_components.assist_google_tv.app_tools import GoogleTVAppsAPI

        api = GoogleTVAppsAPI(self.hass, self.entry)
        instance = await api.async_get_api_instance(context)
        self.assertEqual([tool.name for tool in instance.tools], [
            "assist_google_tv__open_app", "assist_google_tv__go_home",
        ])
        result = await instance.tools[0].async_call(
            self.hass,
            SimpleNamespace(tool_args={"app_name": "YouTube"}),
            context,
        )
        self.assertEqual(result.data["status"], "app_launch_requested")
        self.hass.services.async_call.assert_awaited_with(
            "remote", "turn_on",
            {"entity_id": "remote.tv", "activity": "https://www.youtube.com"},
            blocking=True, context=context.context,
        )
        home_result = await instance.tools[1].async_call(
            self.hass, SimpleNamespace(tool_args={}), context,
        )
        self.assertEqual(home_result.data["status"], "home_navigation_requested")
        self.hass.services.async_call.assert_awaited_with(
            "remote", "send_command", {"entity_id": "remote.tv", "command": "HOME"},
            blocking=True, context=context.context,
        )

    async def test_google_tv_adb_app_stop_does_not_power_off_tv(self):
        context = self._llm_context()
        self.entry.options.update({
            "tv_method": "adb",
            "tv_entity_id": "media_player.tv",
            "tv_apps": '[{"name":"Netflix","launch":"com.netflix.ninja"}]',
        })
        from custom_components.assist_google_tv.app_tools import GoogleTVAppsAPI

        instance = await GoogleTVAppsAPI(self.hass, self.entry).async_get_api_instance(context)
        self.assertEqual([tool.name for tool in instance.tools], [
            "assist_google_tv__open_app", "assist_google_tv__go_home", "assist_google_tv__stop_app",
        ])
        home_result = await instance.tools[1].async_call(
            self.hass, SimpleNamespace(tool_args={}), context,
        )
        self.assertEqual(home_result.data["status"], "home_navigation_requested")
        self.hass.services.async_call.assert_awaited_with(
            "androidtv", "adb_command", {"entity_id": "media_player.tv", "command": "HOME"},
            blocking=True, context=context.context,
        )
        self.hass.services.async_call.reset_mock()
        result = await instance.tools[2].async_call(
            self.hass, SimpleNamespace(tool_args={"app_name": "Netflix"}), context,
        )
        self.assertEqual(result.data["status"], "app_stop_requested")
        self.hass.services.async_call.assert_awaited_once_with(
            "media_player", "select_source",
            {"entity_id": "media_player.tv", "source": "!com.netflix.ninja"},
            blocking=True, context=context.context,
        )

    async def test_netflix_assist_provider_is_separate_and_needs_no_youtube_key(self):
        context = self._llm_context()
        self.states["remote.tv"] = SimpleNamespace(
            entity_id="remote.tv", state="on", attributes={"friendly_name": "Living room TV"},
        )
        self.hass.data[services.DOMAIN].pop("api_key")
        api = llm_tools.NetflixAPI(self.hass)
        instance = await api.async_get_api_instance(context)
        self.assertEqual(api.name, "Assist Google TV (Netflix)")
        self.assertEqual(len(instance.tools), 1)
        self.assertEqual(instance.tools[0].name, "assist_google_tv__netflix_play")
        args = {"query": "Frieren", "season": 2, "episode": 8, "entity_id": "remote.tv"}
        result = await instance.tools[0].async_call(
            self.hass, SimpleNamespace(tool_args=args), context,
        )
        self.assertEqual(result.data["status"], "playback_requested")
        self.hass.services.async_call.assert_awaited_once_with(
            "assist_google_tv", "netflix_play", args, blocking=True, context=context.context,
        )

    async def test_setup_and_options_without_frontend(self):
        self.assertEqual(len(self.hass.services.actions), 6)
        self.entry.options = {"api_key": uuid.uuid4().hex}
        await integration._async_update_options(self.hass, self.entry)
        self.assertEqual(self.hass.data[services.DOMAIN]["api_key"], self.entry.options["api_key"])
        await integration.async_setup(self.hass, {})
        self.assertEqual(len(self.hass.services.actions), 6)

    async def test_netflix_play_resolves_episode_and_sends_app_link(self):
        with patch.object(services, "_async_netflix_title_id", AsyncMock(return_value="81726714")), \
                patch.object(services, "_async_netflix_episode_id", AsyncMock(return_value="82656797")):
            await self.hass.services.invoke("netflix_play", {
                "query": "Frieren", "season": 2, "episode": 8, "entity_id": "remote.tv",
            })
        self.hass.services.async_call.assert_awaited_once_with(
            "remote", "turn_on", {
                "entity_id": "remote.tv",
                "activity": "https://www.netflix.com/watch/82656797?source=30",
            }, blocking=True,
        )

    async def test_netflix_play_dismisses_foreground_screensaver_before_launch(self):
        self.states["remote.tv"] = SimpleNamespace(
            entity_id="remote.tv", state="on",
            attributes={"current_activity": "com.google.android.apps.tv.dreamx/.service.Backdrop"},
        )
        with patch.object(services, "_async_netflix_title_id", AsyncMock(return_value="81161626")), \
                patch.object(services, "_async_netflix_is_movie", AsyncMock(return_value=True)):
            await self.hass.services.invoke("netflix_play", {
                "query": "Red Notice", "entity_id": "remote.tv",
            })
        self.assertEqual(
            self.hass.services.async_call.await_args_list,
            [
                call("remote", "send_command", {
                    "entity_id": "remote.tv", "command": "BACK",
                }, blocking=True),
                call("remote", "turn_on", {
                    "entity_id": "remote.tv",
                    "activity": "https://www.netflix.com/watch/81161626?source=30",
                }, blocking=True),
            ],
        )

    async def test_youtube_play_dismisses_remote_screensaver_first(self):
        self.hass.data[services.DOMAIN][services.CONF_PLAYBACK_MODE] = "youtube_app_fallback"
        self.states["remote.tv"] = SimpleNamespace(
            entity_id="remote.tv", state="on",
            attributes={"current_activity": "com.google.android.backdrop/.Backdrop"},
        )
        await services._async_play_video(self.hass, "dQw4w9WgXcQ", "remote.tv")
        self.assertEqual(
            self.hass.services.async_call.await_args_list,
            [
                call("remote", "send_command", {
                    "entity_id": "remote.tv", "command": "BACK",
                }, blocking=True),
                call("remote", "turn_on", {
                    "entity_id": "remote.tv",
                    "activity": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                }, blocking=True),
            ],
        )

    async def test_cast_play_dismisses_configured_adb_screensaver_first(self):
        self.hass.data[services.DOMAIN].update({
            services.CONF_PLAYBACK_MODE: "cast",
            "tv_method": "adb",
            "tv_entity_id": "media_player.android_tv",
        })
        self.states["media_player.android_tv"] = SimpleNamespace(
            entity_id="media_player.android_tv", state="idle",
            attributes={"app_id": "com.android.dreams.basic"},
        )
        await services._async_play_video(self.hass, "dQw4w9WgXcQ", "media_player.tv")
        self.assertEqual(
            self.hass.services.async_call.await_args_list,
            [
                call("androidtv", "adb_command", {
                    "entity_id": "media_player.android_tv", "command": "BACK",
                }, blocking=True),
                call("media_player", "play_media", {
                    "entity_id": "media_player.tv",
                    "media_content_type": "cast",
                    "media_content_id": '{"app_name": "youtube", "media_id": "dQw4w9WgXcQ"}',
                }, blocking=True),
            ],
        )

    async def test_netflix_movie_without_episode_opens_watch_link(self):
        with patch.object(services, "_async_netflix_title_id", AsyncMock(return_value="81161626")), \
                patch.object(services, "_async_netflix_is_movie", AsyncMock(return_value=True)):
            await self.hass.services.invoke("netflix_play", {
                "query": "Red Notice", "entity_id": "remote.tv",
            })
        self.hass.services.async_call.assert_awaited_once_with(
            "remote", "turn_on", {
                "entity_id": "remote.tv",
                "activity": "https://www.netflix.com/watch/81161626?source=30",
            }, blocking=True,
        )

    async def test_netflix_series_without_episode_opens_title_page(self):
        with patch.object(services, "_async_netflix_title_id", AsyncMock(return_value="81726714")), \
                patch.object(services, "_async_netflix_is_movie", AsyncMock(return_value=False)):
            await self.hass.services.invoke("netflix_play", {
                "query": "Frieren", "entity_id": "remote.tv",
            })
        self.hass.services.async_call.assert_awaited_once_with(
            "remote", "turn_on", {
                "entity_id": "remote.tv",
                "activity": "https://www.netflix.com/title/81726714?source=30",
            }, blocking=True,
        )

    async def test_netflix_title_kind_reads_top_level_video_metadata(self):
        movie = '"topLevelVideoId":81161626,"type":"Movie","videoId":81161626'
        series = '"topLevelVideoId":81726714,"type":"Show","videoId":81726714'
        with patch.object(services, "_async_netflix_request", AsyncMock(return_value=movie)):
            self.assertTrue(await services._async_netflix_is_movie(self.hass, "81161626"))
        with patch.object(services, "_async_netflix_request", AsyncMock(return_value=series)):
            self.assertFalse(await services._async_netflix_is_movie(self.hass, "81726714"))

    async def test_netflix_play_rejects_partial_episode_and_wrong_target_before_lookup(self):
        with patch.object(services, "_async_netflix_title_id", AsyncMock()) as lookup:
            with self.assertRaises(HAError):
                await self.hass.services.invoke("netflix_play", {
                    "query": "Frieren", "season": 2, "entity_id": "remote.tv",
                })
            with self.assertRaises(vol.Invalid):
                await self.hass.services.invoke("netflix_play", {
                    "query": "Frieren", "entity_id": "media_player.tv",
                })
            lookup.assert_not_awaited()

    async def test_netflix_episode_parser_uses_season_edges_and_global_numbers(self):
        html = (
            '{"__typename":"Show","seasons":{"edges":['
            '{"node":{"__typename":"Season","episodes":{"edges":['
            '{"node":{"__typename":"Episode","videoId":100,"number":1}},'
            '{"node":{"__typename":"Episode","videoId":101,"number":2}}]}}},'
            '{"node":{"__typename":"Season","episodes":{"edges":['
            '{"node":{"__typename":"Episode","videoId":200,"number":49}},'
            '{"node":{"__typename":"Episode","videoId":201,"number":50}},'
            '{"node":{"__typename":"Episode","videoId":202,"number":51}},'
            '{"node":{"__typename":"Episode","videoId":203,"number":52}}]}}}]}'
        )
        self.assertEqual(
            services._netflix_episode_seasons(html),
            [[(1, 100), (2, 101)], [(49, 200), (50, 201), (51, 202), (52, 203)]],
        )
        with patch.object(services, "_async_netflix_request", AsyncMock(return_value=html)):
            self.assertEqual(await services._async_netflix_episode_id(self.hass, "999", 2, 4), "203")
            self.assertEqual(await services._async_netflix_episode_id(self.hass, "999", None, 52), "203")

    async def test_netflix_title_lookup_decodes_localized_search_links(self):
        response = ('<div class="result"><div class="result__title"><a class="result__a" '
                    'href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.netflix.com%2Fkr%2Ftitle%2F81726714&amp;rut=abc">'
                    '장송의 프리렌</a></div><div class="result__snippet">Netflix</div></div>')
        with patch.object(services, "_async_netflix_search_httpx", AsyncMock(return_value=(200, response))) as request:
            title_id = await services._async_netflix_title_id(self.hass, "장송의 프리렌")
        self.assertEqual(title_id, "81726714")
        self.assertEqual(request.call_args.args[0], {
            "q": "site:netflix.com/kr/title 장송의 프리렌", "b": "", "kl": "", "kp": "-1",
        })

    async def test_netflix_title_lookup_skips_search_challenge_pages(self):
        with patch.object(services, "_async_netflix_search_httpx", AsyncMock(return_value=(202, "<form id='challenge-form'></form>"))):
            with patch.object(services, "_async_netflix_search_curl", AsyncMock(return_value=(202, "<form id='challenge-form'></form>"))) as retry:
                with self.assertRaisesRegex(HAError, "blocked by DuckDuckGo"):
                    await services._async_netflix_title_id(self.hass, "Frieren")
        retry.assert_awaited_once()

    async def test_netflix_title_lookup_retries_challenge_with_curl_and_parses_result(self):
        self.hass.data[services.DOMAIN]["netflix_search_region"] = "us"
        result_html = ('<div class="result"><a class="result__a" '
                       'href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.netflix.com%2Ftitle%2F81726714">'
                       'Frieren</a></div>')
        with patch.object(services, "_async_netflix_search_httpx", AsyncMock(return_value=(202, "<form id='challenge-form'></form>"))), \
                patch.object(services, "_async_netflix_search_curl", AsyncMock(return_value=(200, result_html))) as retry:
            title_id = await services._async_netflix_title_id(self.hass, "Frieren")
        self.assertEqual(title_id, "81726714")
        retry.assert_awaited_once_with({
            "q": "site:netflix.com/us/title Frieren", "b": "", "kl": "", "kp": "-1",
        })

    async def test_netflix_title_lookup_ignores_non_result_links(self):
        response = '<a href="https://www.netflix.com/title/11111111">navigation</a><div class="result"><a class="result__a" href="https://example.com/title/22222222">unrelated</a></div>'
        with patch.object(services, "_async_netflix_search_httpx", AsyncMock(return_value=(200, response))):
            with self.assertRaisesRegex(HAError, "no usable results"):
                await services._async_netflix_title_id(self.hass, "Frieren")

    async def test_video_search_and_cast_payload(self):
        with patch.object(services, "_async_youtube_request", AsyncMock(return_value={"items": [{"id": {"videoId": "dQw4w9WgXcQ"}}]})) as request:
            await self.hass.services.invoke("youtube_search_play", {"query": " music ", "entity_id": "media_player.tv"})
        self.assertEqual(request.call_args.args[2]["type"], "video")
        self.assertEqual(request.call_args.args[2]["q"], "music")
        args = self.hass.services.async_call.call_args
        self.assertEqual(json.loads(args.args[2]["media_content_id"]), {"app_name": "youtube", "media_id": "dQw4w9WgXcQ"})
        self.assertTrue(args.kwargs["blocking"])

    # Exercise the Android TV Remote app-link branch; related: config_flow/services.py.
    async def test_app_link_playback_sends_youtube_url_to_remote(self):
        self.hass.data[services.DOMAIN]["playback_mode"] = "youtube_app_fallback"
        with patch.object(services, "_async_youtube_request", AsyncMock(return_value={"items": [{"id": {"videoId": "dQw4w9WgXcQ"}}]})):
            await self.hass.services.invoke("youtube_search_play", {"query": "music", "entity_id": "remote.tv"})
        self.hass.services.async_call.assert_awaited_once_with(
            "remote", "turn_on", {
                "entity_id": "remote.tv",
                "activity": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            }, blocking=True,
        )

    async def test_app_link_assist_lists_only_android_tv_remote(self):
        context = self._llm_context()
        self.hass.data[services.DOMAIN]["playback_mode"] = "youtube_app_fallback"
        self.states["remote.tv"] = SimpleNamespace(
            entity_id="remote.tv", state="on", attributes={"friendly_name": "Google TV"},
        )
        result = await llm_tools.YouTubeAPI(self.hass).async_get_api_instance(context)
        self.assertIn("remote.tv", result.api_prompt)
        self.assertIn("media_player.tv", result.api_prompt)

    # SmartTube uses its app link while retaining Android TV Remote target validation.
    async def test_smarttube_mode_sends_smarttube_deep_link(self):
        self.hass.data[services.DOMAIN]["playback_mode"] = "smarttube_fallback"
        with patch.object(services, "_async_youtube_request", AsyncMock()):
            await self.hass.services.invoke(
                "youtube_search_play", {"video": "dQw4w9WgXcQ", "entity_id": "remote.tv"},
            )
        self.hass.services.async_call.assert_awaited_once_with(
            "remote", "turn_on", {
                "entity_id": "remote.tv",
                "activity": "vnd.youtube.launch://www.youtube.com/watch?v=dQw4w9WgXcQ",
            }, blocking=True,
        )

    async def test_smarttube_cast_fallback_runs_after_app_link_error(self):
        self.hass.data[services.DOMAIN]["playback_mode"] = "cast_fallback"
        self.hass.services.async_call.side_effect = [HAError("link could not be opened"), None]
        with patch.object(services, "_async_youtube_request", AsyncMock()) as request:
            await self.hass.services.invoke("youtube_search_play", {
                "video": "dQw4w9WgXcQ", "entity_id": "remote.tv",
                "cast_entity_id": "media_player.tv",
            })
        request.assert_not_awaited()
        self.assertEqual(self.hass.services.async_call.await_count, 2)
        first, second = self.hass.services.async_call.await_args_list
        self.assertEqual(first.args[:2], ("remote", "turn_on"))
        self.assertEqual(first.args[2]["activity"], "vnd.youtube.launch://www.youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertEqual(second.args[:2], ("media_player", "play_media"))
        self.assertEqual(second.args[2]["entity_id"], "media_player.tv")

    async def test_youtube_app_failure_also_uses_cast_fallback(self):
        self.hass.data[services.DOMAIN]["playback_mode"] = "youtube_app_fallback"
        self.hass.services.async_call.side_effect = [HAError("remote failed"), None]
        with patch.object(services, "_async_youtube_request", AsyncMock()):
            await self.hass.services.invoke("youtube_search_play", {
                "video": "dQw4w9WgXcQ", "entity_id": "remote.tv",
                "cast_entity_id": "media_player.tv",
            })
        first, second = self.hass.services.async_call.await_args_list
        self.assertEqual(first.args[2]["activity"], "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertEqual(second.args[:2], ("media_player", "play_media"))

    async def test_smarttube_cast_fallback_requires_cast_target(self):
        self.hass.data[services.DOMAIN]["playback_mode"] = "cast_fallback"
        self.hass.services.async_call.side_effect = HAError("failed")
        with self.assertRaisesRegex(HAError, "valid Cast fallback entity"):
            await self.hass.services.invoke("youtube_search_play", {
                "video": "dQw4w9WgXcQ", "entity_id": "remote.tv",
            })
        self.assertEqual(self.hass.services.async_call.await_count, 1)

    async def test_direct_youtube_video_input_skips_search(self):
        for value in [
            "dQw4w9WgXcQ",
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42",
            "https://youtu.be/dQw4w9WgXcQ?t=42",
            "https://m.youtube.com/shorts/dQw4w9WgXcQ",
            "https://youtube.com/embed/dQw4w9WgXcQ",
            "https://youtube.com/live/dQw4w9WgXcQ",
        ]:
            with self.subTest(value=value), patch.object(services, "_async_youtube_request", AsyncMock()) as request:
                await self.hass.services.invoke("youtube_search_play", {"video": value, "entity_id": "media_player.tv"})
                request.assert_not_awaited()
                args = self.hass.services.async_call.call_args
                self.assertEqual(
                    json.loads(args.args[2]["media_content_id"]),
                    {"app_name": "youtube", "media_id": "dQw4w9WgXcQ"},
                )

    async def test_direct_video_input_validation_and_query_exclusivity(self):
        for data in [
            {"video": "https://example.com/watch?v=dQw4w9WgXcQ", "entity_id": "media_player.tv"},
            {"video": "https://youtube.com/playlist?list=PL123", "entity_id": "media_player.tv"},
            {"video": "too-short", "entity_id": "media_player.tv"},
            {"query": "music", "video": "dQw4w9WgXcQ", "entity_id": "media_player.tv"},
            {"entity_id": "media_player.tv"},
        ]:
            with self.subTest(data=data), self.assertRaises(HAError):
                await self.hass.services.invoke("youtube_search_play", data)

    async def test_empty_results_and_unconfigured_actions(self):
        with patch.object(services, "_async_youtube_request", AsyncMock(return_value={"items": []})):
            with self.assertRaises(HAError):
                await self.hass.services.invoke("youtube_search_play", {"query": "music", "entity_id": "media_player.tv"})
        await integration.async_unload_entry(self.hass, self.entry)
        with self.assertRaises(HAError):
            await self.hass.services.invoke("youtube_search_play", {"query": "music", "entity_id": "media_player.tv"})

    async def test_input_validation(self):
        with self.assertRaises(HAError):
            await self.hass.services.invoke("youtube_search_play", {"query": "music", "entity_id": "light.room"})
        with self.assertRaises(HAError):
            await self.hass.services.invoke("youtube_search_play", {"query": " ", "entity_id": "media_player.tv"})
        with self.assertRaises(vol.Invalid):
            await self.hass.services.invoke("youtube_playlist_save", {"playlist_id": "music", "video_ids": "invalid"})

    async def test_playlist_merge_csv_list_and_delete(self):
        with patch.object(services, "_async_youtube_request", AsyncMock(return_value={"items": []})) as request:
            await self.hass.services.invoke("youtube_playlist_save", {"playlist_id": "my-list", "video_ids": "dQw4w9WgXcQ,dQw4w9WgXcQ"})
            await self.hass.services.invoke("youtube_playlist_save", {"playlist_id": "my-list", "video_ids": ["jNQXAC9IVRw"]})
        self.assertEqual(request.call_args.args[1], "videos")
        state = self.states["youtube_content_search.playlist_my_list"]
        self.assertEqual(len(json.loads(state.attributes["data"])), 2)
        await self.hass.services.invoke("youtube_playlist_delete", {"id": "my-list"})
        self.assertFalse(self.states)

    async def test_playlist_state_id_is_valid_for_rescene(self):
        with patch.object(services, "_async_youtube_request", AsyncMock(return_value={"items": []})):
            await self.hass.services.invoke(
                "youtube_playlist_save", {"playlist_id": "resc ene", "video_ids": ["dQw4w9WgXcQ"]}
            )
        self.assertIn("youtube_content_search.playlist_resc_ene", self.states)
        self.assertNotIn("youtube_content_search._playlist_resc_ene", self.states)

    async def test_playlist_list_returns_summaries_and_video_details(self):
        playlists = self.hass.data[services.DOMAIN][playlist_store.DATA_PLAYLIST_STORE]
        await playlists.async_merge("music", [{
            "videoId": "dQw4w9WgXcQ", "title": "Never Gonna Give You Up",
            "channel": "Rick Astley", "thumbnail": "https://example.com/thumb.jpg",
        }])
        response_handler, _schema, supports_response = self.hass.services.actions["youtube_playlist_list"]
        self.assertEqual(supports_response, SupportsResponse.ONLY)
        summaries = await self.hass.services.invoke("youtube_playlist_list", {})
        self.assertEqual(summaries, {"playlists": [{"playlist_id": "music", "video_count": 1}]})
        details = await self.hass.services.invoke("youtube_playlist_list", {"playlist_id": "music"})
        self.assertEqual(details["videos"][0]["position"], 1)
        self.assertEqual(details["videos"][0]["video_id"], "dQw4w9WgXcQ")
        self.assertEqual(details["videos"][0]["channel"], "Rick Astley")

    async def test_playlist_play_cast_queues_all_videos_in_order(self):
        playlists = self.hass.data[services.DOMAIN][playlist_store.DATA_PLAYLIST_STORE]
        await playlists.async_merge("music", [
            {"videoId": "dQw4w9WgXcQ", "title": "First"},
            {"videoId": "jNQXAC9IVRw", "title": "Second"},
        ])
        await self.hass.services.invoke("youtube_playlist_play", {
            "playlist_id": "music", "entity_id": "media_player.tv",
        })
        calls = self.hass.services.async_call.call_args_list
        self.assertEqual(len(calls), 2)
        first = json.loads(calls[0].args[2]["media_content_id"])
        second = json.loads(calls[1].args[2]["media_content_id"])
        self.assertEqual(first, {"app_name": "youtube", "media_id": "dQw4w9WgXcQ"})
        self.assertEqual(second, {"app_name": "youtube", "media_id": "jNQXAC9IVRw", "enqueue": True})

    async def test_playlist_play_starts_remote_then_queues_remaining_cast_videos(self):
        playlists = self.hass.data[services.DOMAIN][playlist_store.DATA_PLAYLIST_STORE]
        await playlists.async_merge("music", [
            {"videoId": "dQw4w9WgXcQ", "title": "First"},
            {"videoId": "jNQXAC9IVRw", "title": "Second"},
        ])
        self.hass.data[services.DOMAIN]["playback_mode"] = "smarttube_fallback"
        await self.hass.services.invoke("youtube_playlist_play", {
            "playlist_id": "music", "entity_id": "remote.tv",
            "cast_entity_id": "media_player.tv",
        })
        calls = self.hass.services.async_call.call_args_list
        self.assertEqual(calls[0].args[:2], ("remote", "turn_on"))
        self.assertEqual(calls[0].args[2]["activity"], "vnd.youtube.launch://www.youtube.com/watch?v=dQw4w9WgXcQ")
        queued = json.loads(calls[1].args[2]["media_content_id"])
        self.assertEqual(queued["media_id"], "jNQXAC9IVRw")
        self.assertTrue(queued["enqueue"])

    async def test_network_failure_does_not_expose_url(self):
        self.hass.session = SimpleNamespace(get=Mock(side_effect=aiohttp.ClientError("sensitive URL omitted")))
        with self.assertRaises(HAError) as error:
            await services._async_youtube_request(self.hass, "search", {})
        self.assertEqual(str(error.exception), "Unable to retrieve YouTube data")
        self.assertIsNone(error.exception.__cause__)

    async def test_http_error(self):
        response = SimpleNamespace(status=403, json=AsyncMock(return_value={}))
        context = SimpleNamespace()
        class ResponseContext:
            async def __aenter__(self):
                return response
            async def __aexit__(self, *args):
                return False
        self.hass.session = SimpleNamespace(get=Mock(return_value=ResponseContext()))
        with self.assertRaisesRegex(HAError, "HTTP 403"):
            await services._async_youtube_request(self.hass, "search", {})

    # Check structured Google errors and redaction without real credentials or requests.
    async def test_api_error_reasons_and_sensitive_data_omitted(self):
        sensitive = self.entry.data["api_key"]
        cases = [
            ({"error": {"errors": [{"reason": "invalidFilters"}]}}, "invalidFilters"),
            ({"error": {"details": [{"reason": "API_KEY_INVALID"}], "status": "INVALID_ARGUMENT"}}, "API_KEY_INVALID, INVALID_ARGUMENT"),
            ({"error": {"details": [{"reason": "SERVICE_DISABLED"}]}}, "SERVICE_DISABLED"),
            ({"error": {"errors": [{"reason": "quotaExceeded"}]}}, "quotaExceeded"),
            ({"error": {"message": sensitive, "errors": [{"reason": sensitive}], "status": sensitive}}, "UNKNOWN"),
            ({"error": {"errors": [None, {"reason": []}], "details": "invalid"}}, "UNKNOWN"),
            ([], "UNKNOWN"),
        ]
        for payload, expected in cases:
            with self.subTest(expected=expected):
                if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
                    payload["error"]["message"] = sensitive
                    payload["error"]["metadata"] = {"url": f"https://example.invalid/?key={sensitive}"}
                response = SimpleNamespace(status=400, json=AsyncMock(return_value=payload))
                class ResponseContext:
                    async def __aenter__(self):
                        return response
                    async def __aexit__(self, *args):
                        return False
                self.hass.session = SimpleNamespace(get=Mock(return_value=ResponseContext()))
                with self.assertRaises(HAError) as error:
                    await services._async_youtube_request(self.hass, "search", {})
                self.assertEqual(str(error.exception), f"YouTube API returned HTTP 400 (reason: {expected})")
                self.assertNotIn(sensitive, str(error.exception))
                self.assertNotIn("https://", str(error.exception))

    async def test_non_json_api_error_keeps_http_status(self):
        response = SimpleNamespace(status=400, json=AsyncMock(side_effect=ValueError("response omitted")))
        class ResponseContext:
            async def __aenter__(self):
                return response
            async def __aexit__(self, *args):
                return False
        self.hass.session = SimpleNamespace(get=Mock(return_value=ResponseContext()))
        with self.assertRaises(HAError) as error:
            await services._async_youtube_request(self.hass, "search", {})
        self.assertEqual(str(error.exception), "YouTube API returned HTTP 400 (reason: UNKNOWN)")
        self.assertIsNone(error.exception.__cause__)

    async def test_config_flow_and_options_empty_input(self):
        flow = flows.YouTubeConfigFlow()
        result = await flow.async_step_user()
        self.assertEqual(result["step_id"], "user")
        api_key_selector = next(
            value for key, value in result["data_schema"].schema.items()
            if getattr(key, "schema", key) == "api_key"
        )
        self.assertEqual(api_key_selector.config["type"], "password")
        result = await flow.async_step_user({"api_key": " "})
        self.assertEqual(result["errors"], {"base": "api_key_required"})
        result = await flow.async_step_user(self.entry.data)
        self.assertEqual(result["step_id"], "tv_control")
        flow.hass = self.hass
        self.states["remote.tv"] = SimpleNamespace(
            entity_id="remote.tv", state="on", attributes={"friendly_name": "Living room TV"},
        )
        result = await flow.async_step_tv_control({"tv_method": "remote", "tv_entity_id": "remote.tv"})
        self.assertEqual(result["step_id"], "apps")
        self.assertIn("tv_selected_apps", result["data_schema"].schema)
        selected_key = next(
            key for key in result["data_schema"].schema
            if getattr(key, "schema", key) == "tv_selected_apps"
        )
        self.assertTrue(result["data_schema"].schema[selected_key].config["multiple"])
        result = await flow.async_step_apps({
            "tv_selected_apps": ["https://www.youtube.com"], "tv_custom_apps": "[]",
        })
        self.assertEqual(result["step_id"], "playback_mode")
        result = await flow.async_step_playback_mode({"playback_mode": "cast_fallback", "netflix_search_region": "kr"})
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["data"]["playback_mode"], "cast_fallback")
        self.assertEqual(result["data"]["netflix_search_region"], "kr")
        self.assertEqual(json.loads(result["data"]["tv_apps"])[0]["name"], "YouTube")
        options = flow.async_get_options_flow(self.entry)
        result = await options.async_step_init({"api_key": " "})
        self.assertEqual(result["step_id"], "tv_control")
        options.hass = self.hass
        result = await options.async_step_tv_control({"tv_method": "remote", "tv_entity_id": "remote.tv"})
        self.assertEqual(result["step_id"], "apps")
        result = await options.async_step_apps({
            "tv_selected_apps": ["https://www.youtube.com"], "tv_custom_apps": "[]",
        })
        self.assertEqual(result["step_id"], "playback_mode")
        result = await options.async_step_playback_mode({"playback_mode": "cast_fallback", "netflix_search_region": "us"})
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["data"]["netflix_search_region"], "us")
        flow._async_current_entries = lambda: [self.entry]
        self.assertEqual((await flow.async_step_user())["reason"], "single_instance_allowed")

    async def test_adb_app_candidates_parse_nested_response(self):
        self.hass.services.async_call.return_value = {
            "media_player.tv": {
                "adb_response": "com.netflix.ninja/.MainActivity\ncom.android.settings/.Settings",
            },
        }
        apps = await flows._adb_tv_launchers(self.hass, "media_player.tv")
        self.assertEqual(apps, [{"name": "Netflix", "launch": "com.netflix.ninja"}])
        self.hass.services.async_call.assert_awaited_once()

    # Discard runtime data and states, then restore only from the saved file.
    async def _restart(self):
        self.hass.data = {}
        self.states.clear()
        await integration.async_setup(self.hass, {})
        await integration.async_setup_entry(self.hass, self.entry)

    async def test_persist_and_restore_after_restart(self):
        with patch.object(services, "_async_youtube_request", AsyncMock(return_value={"items": []})):
            await self.hass.services.invoke("youtube_playlist_save", {"playlist_id": "music", "video_ids": ["dQw4w9WgXcQ"]})
        await self._restart()
        videos = json.loads(self.states["youtube_content_search.playlist_music"].attributes["data"])
        self.assertEqual([v["videoId"] for v in videos], ["dQw4w9WgXcQ"])

    async def test_renamed_domain_keeps_legacy_playlist_storage_contract(self):
        self.assertEqual(services.DOMAIN, "assist_google_tv")
        self.assertEqual(playlist_store.STORAGE_KEY, "youtube_content_search.playlists")
        self.assertEqual(playlist_store._ENTITY_PREFIX, "youtube_content_search.playlist_")

    async def test_deletion_survives_restart(self):
        with patch.object(services, "_async_youtube_request", AsyncMock(return_value={"items": []})):
            await self.hass.services.invoke("youtube_playlist_save", {"playlist_id": "music", "video_ids": ["dQw4w9WgXcQ"]})
        await self.hass.services.invoke("youtube_playlist_delete", {"id": "music"})
        await self._restart()
        self.assertFalse(self.states)

    async def test_concurrent_saves_survive_restart(self):
        with patch.object(services, "_async_youtube_request", AsyncMock(return_value={"items": []})):
            await asyncio.gather(*[
                self.hass.services.invoke("youtube_playlist_save", {"playlist_id": "music", "video_ids": [video]})
                for video in ["dQw4w9WgXcQ", "jNQXAC9IVRw", "dQw4w9WgXcQ"]
            ])
        await self._restart()
        videos = json.loads(self.states["youtube_content_search.playlist_music"].attributes["data"])
        self.assertEqual({v["videoId"] for v in videos}, {"dQw4w9WgXcQ", "jNQXAC9IVRw"})

    async def test_save_failure_retains_runtime_and_disk(self):
        repo = self.hass.data[services.DOMAIN][services.DATA_PLAYLIST_STORE]
        await repo.async_merge("music", [{"videoId": "dQw4w9WgXcQ"}])
        with patch.object(repo.store, "async_save", AsyncMock(side_effect=OSError())):
            with self.assertRaises(HAError):
                await repo.async_delete("music")
        self.assertIn("youtube_content_search.playlist_music", self.states)
        await self._restart()
        self.assertIn("youtube_content_search.playlist_music", self.states)

    async def test_silent_write_failure_detected(self):
        repo = self.hass.data[services.DOMAIN][services.DATA_PLAYLIST_STORE]
        await repo.async_merge("music", [{"videoId": "dQw4w9WgXcQ"}])
        with patch.object(repo.store, "async_save", AsyncMock()):
            with self.assertRaises(HAError):
                await repo.async_delete("music")
        self.assertIn("music", repo.playlists)

    async def test_legacy_states_imported_once(self):
        await integration.async_unload_entry(self.hass, self.entry)
        self.hass.states.async_set("youtube_content_search._playlist_legacy", "on", {
            "data": json.dumps([{"videoId": "dQw4w9WgXcQ"}]),
        })
        await integration.async_setup_entry(self.hass, self.entry)
        await self._restart()
        self.assertIn("youtube_content_search.playlist_legacy", self.states)
        self.assertNotIn("youtube_content_search._playlist_legacy", self.states)

    async def test_rescene_playlist_restores_to_valid_home_assistant_entity_id(self):
        repo = self.hass.data[services.DOMAIN][services.DATA_PLAYLIST_STORE]
        await repo.store.async_save({
            "playlists": {"rescene": [{"videoId": "dQw4w9WgXcQ"}]},
        })
        await self._restart()
        self.assertIn("youtube_content_search.playlist_rescene", self.states)
        self.assertEqual(
            json.loads(self.states["youtube_content_search.playlist_rescene"].attributes["data"])[0]["videoId"],
            "dQw4w9WgXcQ",
        )

    async def test_invalid_storage_not_overwritten(self):
        repo = self.hass.data[services.DOMAIN][services.DATA_PLAYLIST_STORE]
        await repo.store.async_save({"playlists": {"music": "invalid"}})
        before = repo.store.path.read_bytes()
        with self.assertRaises(HAError):
            await self._restart()
        self.assertEqual(repo.store.path.read_bytes(), before)
        self.assertFalse(self.states)

    async def test_reload_preserves_saved_playlists(self):
        repo = self.hass.data[services.DOMAIN][services.DATA_PLAYLIST_STORE]
        await repo.async_merge("music", [{"videoId": "dQw4w9WgXcQ"}])
        await integration.async_unload_entry(self.hass, self.entry)
        self.assertFalse(self.states)
        await integration.async_setup_entry(self.hass, self.entry)
        self.assertIn("youtube_content_search.playlist_music", self.states)

    async def test_stale_repository_cannot_write_after_unload(self):
        repo = self.hass.data[services.DOMAIN][services.DATA_PLAYLIST_STORE]
        await integration.async_unload_entry(self.hass, self.entry)
        await integration.async_setup_entry(self.hass, self.entry)
        with self.assertRaises(HAError):
            await repo.async_merge("stale", [{"videoId": "dQw4w9WgXcQ"}])
        self.assertFalse(self.states)


if __name__ == "__main__":
    unittest.main()
