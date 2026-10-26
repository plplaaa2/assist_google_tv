"""Assist Google TV service and HTTP handlers."""

import asyncio
import json as _json_module
import html as _html_module
from html.parser import HTMLParser
import aiohttp
import aiohttp.web
import httpx
from curl_cffi.requests import AsyncSession as CurlAsyncSession
import logging
import urllib.parse
import re
import voluptuous as vol
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from typing import Any, Optional
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from .const import (
    CONF_API_KEY, CONF_PLAYBACK_MODE, DEFAULT_PLAYBACK_MODE, DOMAIN,
    PLAYBACK_MODE_APP_LINKS, PLAYBACK_MODE_CAST, PLAYBACK_MODE_SMARTTUBE,
    PLAYBACK_MODE_CAST_FALLBACK,
)
from .playlist_store import DATA_PLAYLIST_STORE, PLAYLIST_ENTITY_PREFIX

_LOGGER = logging.getLogger(__name__)


def _get_api_key(hass: HomeAssistant) -> Optional[str]:
    """Retrieve API key safely from hass.data."""
    config = hass.data.get(DOMAIN, {})
    if isinstance(config, dict):
        return config.get(CONF_API_KEY)
    # Also try entry data (for setup_entry path)
    if "api_key" in hass.data and isinstance(hass.data["api_key"], str):
        return hass.data["api_key"]
    return None


def _sanitize_entity_id(playlist_id: str) -> Optional[str]:
    """Sanitize playlist_id for use as an HA entity ID."""
    # Use valid HA object IDs; related: service playlist save/delete actions.
    sanitized = re.sub(r"[^a-z0-9_]", "_", playlist_id.strip().lower())
    return sanitized if sanitized.strip("_") else None


# ──────────────────────────── REST API Handlers (HTTP Endpoints) ────────────

async def async_handle_youtube_search(hass: HomeAssistant, request: aiohttp.web.Request) -> Any:
    """Handle /youtube-search POST from web UI."""
    api_key = _get_api_key(hass)
    if not api_key:
        return aiohttp.web.json_response({"error": "API key not configured"}, status=401)

    try:
        if request.content_type == 'application/json':
            query_body = await request.json() or {}
            q = query_body.get("query", "")
            max_results = int(query_body.get("maxResults", 15))
        else:
            raw_text = (await request.text()).strip()
            q = urllib.parse.unquote(raw_text)
            max_results = 15

    except Exception as e:
        return aiohttp.web.json_response({"error": "Invalid request body"}, status=400)

    if not q or not isinstance(q, str):
        return aiohttp.web.json_response({"error": "Empty query"}, status=400)

    url = (
        f"https://www.googleapis.com/youtube/v3/search?"
        f"part=snippet&type=video&maxResults={max_results}&q={urllib.parse.quote(q)}&key={api_key}"
    )

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    _LOGGER.error("YouTube API error: %s", resp.status)
                    return aiohttp.web.json_response({"error": f"API error {resp.status}"}, status=500)
                data = await resp.json()

    except Exception as e:
        _LOGGER.exception("Error during YouTube search response fetch: %s", e)
        return aiohttp.web.json_response({"error": str(e)}, status=500)

    items = data.get("items") or []
    videos = []
    for item in items:
        vid = item.get("id", {})
        video_id = vid.get("videoId", "")
        if not video_id:
            continue

        thm_data = []
        ths = (item.get("snippet") or {}).get("thumbnails") or {}
        for size_name in ["default", "medium", "high", "maxres"]:
            if size_name in ths:
                th_info = ths[size_name]
                url_val = th_info["url"] if isinstance(th_info, dict) else (str(th_info) if th_info else "")
                thm_data.append({
                    "width": None,
                    "height": None,
                    "url": url_val or ""
                })

        videos.append({
            "id": video_id,
            "title": (item.get("snippet") or {}).get("title") or "",
            "description": (item.get("snippet") or {}).get("description") or "",
            "channelName": (item.get("snippet") or {}).get("channelTitle") or "",
            "duration": None,
            "thumbnails": thm_data,
        })

    return aiohttp.web.json_response({"results": videos})


async def async_handle_playlist_detail(hass: HomeAssistant, request: aiohttp.web.Request) -> Any:
    """Handle /playlist-detail/{id} GET from web UI."""
    api_key = _get_api_key(hass)
    if not api_key:
        return aiohttp.web.json_response({"error": "API key not configured"}, status=401)

    try:
        playlist_id = request.match_info["playlist_id"]
    except KeyError as e:
        _LOGGER.error("Missing playlist_id in URL path: %s", e)
        return aiohttp.web.json_response({"error": "Playlist ID not found"}, status=400)

    # Fetch videos from the playlist via YouTube Data API v3 playlists.list + items.list
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://www.googleapis.com/youtube/v3/playlists?part=id&playlistId={playlist_id}&key={api_key}"
            async with session.get(url) as resp:
                if resp.status != 200:
                    _LOGGER.error("YouTube API playlist error: %s", resp.status)
                    return aiohttp.web.json_response({"error": f"API error {resp.status}"}, status=500)

            pl_data = await resp.json()
            items_list = [i["id"] for i in (pl_data.get("items") or [])]

    except Exception as e:
        _LOGGER.exception("Error fetching playlist info: %s", e)
        return aiohttp.web.json_response({"error": str(e)}, status=500)

    if not items_list:
        return aiohttp.web.json_response({"playlist_id": playlist_id, "videos": []})

    # Fetch individual video IDs via search
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&id={','.join(items_list)}&type=video&key={api_key}"
            async with session.get(url) as resp:
                if resp.status != 200:
                    _LOGGER.error("YouTube API search error: %s", resp.status)
                    return aiohttp.web.json_response({"error": f"API error {resp.status}"}, status=500)

            data = await resp.json()
            items = data.get("items") or []
            videos = []
            for item in items:
                vid = item.get("id", {})
                video_id = vid.get("videoId", "") if isinstance(vid, dict) else str(vid)

                thm_data = []
                ths = (item.get("snippet") or {}).get("thumbnails") or {}
                for size_name in ["default", "medium", "high"]:
                    if size_name in ths:
                        th_info = ths[size_name]
                        url_val = th_info.get("url") if isinstance(th_info, dict) else (str(th_info) if th_info else "")
                        thm_data.append({
                            "width": None,
                            "height": None,
                            "url": url_val or ""
                        })

                videos.append({
                    "videoId": video_id,
                    "title": item.get("snippet", {}).get("title") or "",
                    "channel": (item.get("snippet") or {}).get("channelTitle") or "",
                    "thumbnail": thm_data,
                })

            return aiohttp.web.json_response({"playlist_id": playlist_id, "videos": videos})

    except Exception as e:
        _LOGGER.exception("Error fetching video details for playlist %s: %s", playlist_id, e)
        return aiohttp.web.json_response({"error": str(e)}, status=500)


async def async_handle_playlist_save(hass: HomeAssistant, request: aiohttp.web.Request) -> Any:
    """Handle /playlist-save POST from web UI (add videos to a playlist)."""

    try:
        data = await request.json() if request.content_type == 'application/json' else {}
        video_ids_str = data.get("video_ids", []) or []
        playlist_id = data.get("playlist_id")
    except Exception as e:
        return aiohttp.web.json_response({"error": "Invalid request body"}, status=400)

    if not playlist_id:
        _LOGGER.error("Missing playlist_id for playlist_save.")
        return aiohttp.web.json_response({"error": "Playlist ID required"}, status=400)

    try:
        video_ids = [str(v).strip() for v in (video_ids_str or [])]

        sanitized_playlist_id = _sanitize_entity_id(str(playlist_id))
        if not sanitized_playlist_id:
            _LOGGER.error("Invalid playlist_id for playlist_save: %s", playlist_id)
            return aiohttp.web.json_response({"error": "Invalid playlist ID"}, status=400)
        entity_id = f"{PLAYLIST_ENTITY_PREFIX}{sanitized_playlist_id}"

        # Get current state data
        new_videos = []
        existing_videos = {}

        states = hass.states.async_all()
        for s in states:
            if s.entity_id == entity_id:
                try:
                    raw_data = (s.attributes or {}).get('data', '[]')
                    parsed = _json_module.loads(raw_data) if isinstance(raw_data, str) else raw_data
                    existing_videos = {v['videoId']: v for v in (parsed or [])}
                    new_videos = list(parsed or [])
                except Exception:
                    pass

        # Add new video IDs that aren't already present
        for vid_id in video_ids:
            if vid_id not in existing_videos:
                existing_videos[vid_id] = {
                    'videoId': vid_id,
                    'title': '',
                    'channel': ''
                }

        updated_list = list(existing_videos.values())
        hass.states.async_set(entity_id, 'on', {'data': _json_module.dumps(updated_list)})

        _LOGGER.info("Playlist save: added %d videos to '%s'", len(video_ids) - sum(1 for v in video_ids if v in existing_videos), playlist_id)

    except Exception as e:
        _LOGGER.exception("Error saving to playlist %s: %s", playlist_id, e)
        return aiohttp.web.json_response({"error": str(e)}, status=500)


async def async_handle_playlist_delete(hass: HomeAssistant, request: aiohttp.web.Request) -> Any:
    """Handle /playlist-delete/{id} DELETE from web UI."""

    try:
        playlist_id = request.match_info["playlist_id"]
        sanitized_playlist_id = _sanitize_entity_id(str(playlist_id))
        if not sanitized_playlist_id:
            _LOGGER.error("Invalid playlist_id for playlist_delete: %s", playlist_id)
            return aiohttp.web.json_response({"error": "Invalid playlist ID"}, status=400)
        entity_id = f"{PLAYLIST_ENTITY_PREFIX}{sanitized_playlist_id}"
        hass.states.async_remove(entity_id)
        return aiohttp.web.json_response({"success": True, "message": f"Playlist '{playlist_id}' deleted"})

    except Exception as e:
        _LOGGER.exception("Error deleting playlist %s: %s", playlist_id, e)
        return aiohttp.web.json_response({"error": str(e)}, status=500)


# ──────────────────────────── Service Functions (Cast Playback / Legacy Mode) ────────────

# Service-only actions use HA's shared HTTP session; related: __init__.py/services.yaml.
def _require_api_key(hass: HomeAssistant) -> str:
    api_key = _get_api_key(hass)
    if not api_key:
        raise ServiceValidationError("Configure Assist Google TV before calling this action")
    return api_key


# Only known constant codes may enter errors; related: tests/test_service_only.py and README.md.
_SAFE_API_ERROR_CODES = frozenset({
    "API_KEY_INVALID", "API_KEY_SERVICE_BLOCKED", "API_KEY_HTTP_REFERRER_BLOCKED",
    "API_KEY_IP_ADDRESS_BLOCKED", "API_KEY_ANDROID_APP_BLOCKED", "API_KEY_IOS_APP_BLOCKED",
    "SERVICE_DISABLED", "BILLING_DISABLED", "CONSUMER_INVALID",
    "INVALID_ARGUMENT", "PERMISSION_DENIED", "UNAUTHENTICATED", "RESOURCE_EXHAUSTED",
    "badRequest", "keyInvalid", "accessNotConfigured", "forbidden", "quotaExceeded",
    "dailyLimitExceeded", "rateLimitExceeded", "incompatibleParameters", "invalidFilters",
    "invalidPageToken", "missingRequiredParameter", "unexpectedParameter", "invalidValue",
    "invalidPart", "unexpectedPart", "unknownPart", "invalidSearchFilter",
})


def _safe_api_error_codes(payload) -> str:
    """Read structured reasons while discarding messages, metadata and unknown strings."""
    error = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(error, dict):
        return "UNKNOWN"
    codes = []
    for field in ("details", "errors"):
        entries = error.get(field, [])
        if not isinstance(entries, list):
            continue
        for entry in entries:
            reason = entry.get("reason") if isinstance(entry, dict) else None
            if isinstance(reason, str) and reason in _SAFE_API_ERROR_CODES and reason not in codes:
                codes.append(reason)
    status = error.get("status")
    if isinstance(status, str) and status in _SAFE_API_ERROR_CODES and status not in codes:
        codes.append(status)
    return ", ".join(codes) if codes else "UNKNOWN"


async def _async_youtube_request(hass: HomeAssistant, resource: str, params: dict) -> dict:
    """Request API data without exposing credential-bearing URLs in errors."""
    params = {**params, "key": _require_api_key(hass)}
    session = async_get_clientsession(hass)
    try:
        async with session.get(
            f"https://www.googleapis.com/youtube/v3/{resource}",
            params=params, timeout=aiohttp.ClientTimeout(total=30),
        ) as response:
            if response.status != 200:
                # Parse only approved reason codes; never expose response text or request URLs.
                try:
                    payload = await response.json()
                except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
                    payload = None
                reasons = _safe_api_error_codes(payload)
                raise HomeAssistantError(
                    f"YouTube API returned HTTP {response.status} (reason: {reasons})"
                ) from None
            return await response.json()
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
        raise HomeAssistantError("Unable to retrieve YouTube data") from None


# Resolve Netflix title/episode IDs from public pages; related: netflix_play action.
async def _async_netflix_request(
    hass: HomeAssistant, url: str, *, headers: dict | None = None, data: dict | None = None,
) -> str:
    """Fetch a public Netflix/search page using Home Assistant's shared session."""
    session = async_get_clientsession(hass)
    try:
        request = session.post if data is not None else session.get
        async with request(url, headers=headers, data=data, timeout=aiohttp.ClientTimeout(total=12)) as response:
            response.raise_for_status()
            return await response.text()
    except (aiohttp.ClientError, asyncio.TimeoutError) as err:
        status = getattr(err, "status", None)
        _LOGGER.warning(
            "Netflix title lookup request failed (%s, HTTP %s)", type(err).__name__, status or "unknown",
        )
        raise HomeAssistantError("Netflix title lookup failed") from None


async def _async_netflix_search_httpx(data: dict[str, str]) -> tuple[int, str]:
    """Issue a bounded DDG HTML request; related: assist_web_search.api.DDGClient._httpx."""
    async with httpx.AsyncClient(timeout=12, trust_env=False) as client:
        async with client.stream(
            "POST", "https://html.duckduckgo.com/html", data=data,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "text/html"},
        ) as response:
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > 2 * 1024 * 1024:
                    raise HomeAssistantError("DuckDuckGo search response exceeded the size limit")
            return response.status_code, body.decode("utf-8", errors="replace")


async def _async_netflix_search_curl(data: dict[str, str]) -> tuple[int, str]:
    """Retry a challenged DDG search with a browser TLS fingerprint; related: assist_web_search.api.DDGClient._curl."""
    body = bytearray()

    def collect(chunk: bytes) -> int:
        if len(body) + len(chunk) > 2 * 1024 * 1024:
            return 0
        body.extend(chunk)
        return len(chunk)

    try:
        async with CurlAsyncSession(impersonate="chrome131", trust_env=False) as session:
            response = await session.post(
                "https://html.duckduckgo.com/html", data=data,
                timeout=12,
                allow_redirects=False, content_callback=collect,
            )
        return response.status_code, body.decode("utf-8", errors="replace")
    except HomeAssistantError:
        raise
    except Exception as err:
        _LOGGER.warning("Netflix title lookup curl retry failed (%s)", type(err).__name__)
        raise HomeAssistantError("Netflix title lookup failed") from None


class _NetflixSearchResultsParser(HTMLParser):
    """Extract DDG result-title links; related: assist_web_search.api.parse_results."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.result_depth = 0
        self.result_div_stack: list[bool] = []
        self.anchor_depth = 0
        self.anchor_href = ""
        self.anchor_text: list[str] = []
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        if tag == "div":
            is_result = "result" in classes
            self.result_div_stack.append(is_result)
            self.result_depth += int(is_result)
        if tag == "a" and self.result_depth and classes.intersection({"result__a", "result__title"}):
            self.anchor_depth = 1
            self.anchor_href = attributes.get("href") or ""
            self.anchor_text = []
        elif self.anchor_depth and tag == "a":
            self.anchor_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self.anchor_depth:
            self.anchor_depth -= 1
            if self.anchor_depth == 0 and self.anchor_href:
                self.links.append(self.anchor_href)
        if tag == "div" and self.result_div_stack:
            self.result_depth -= int(self.result_div_stack.pop())


async def _async_netflix_title_id(hass: HomeAssistant, query: str) -> str:
    """Resolve Netflix title IDs with standalone DDG request and parsing code."""
    search_query = f"site:netflix.com/title {query}"
    search_data = {"q": search_query, "b": "", "kl": "", "kp": "-1"}
    try:
        status, html = await _async_netflix_search_httpx(search_data)
    except Exception as err:
        _LOGGER.warning("Netflix title lookup HTTP request failed (%s); trying curl backend", type(err).__name__)
        status, html = 0, ""

    def blocked(response_status: int, response_html: str) -> bool:
        sample = response_html[:10000].lower()
        return response_status in (202, 403) or not response_html.strip() or any(
            marker in sample for marker in ("anomaly.js", "anomaly-modal", "captcha", "challenge-form")
        )

    if status == 429:
        raise HomeAssistantError("DuckDuckGo search rate limit reached")
    if blocked(status, html):
        _LOGGER.warning("Netflix title lookup provider DuckDuckGo returned a challenge page")
        try:
            status, html = await _async_netflix_search_curl(search_data)
        except Exception as err:
            _LOGGER.warning("Netflix title lookup curl retry failed (%s)", type(err).__name__)
            raise HomeAssistantError("Netflix title lookup request failed") from None
        if status == 429:
            raise HomeAssistantError("DuckDuckGo search rate limit reached")
        if blocked(status, html):
            _LOGGER.warning("Netflix title lookup curl retry returned blocked HTTP %s", status)
            raise HomeAssistantError("Netflix title lookup was blocked by DuckDuckGo")
    if status != 200:
        _LOGGER.warning("Netflix title lookup returned HTTP %s", status)
        raise HomeAssistantError("Netflix title lookup request failed")

    parser = _NetflixSearchResultsParser()
    parser.feed(html)
    candidates = []
    for link in parser.links:
        resolved = urllib.parse.urljoin("https://html.duckduckgo.com/html", _html_module.unescape(link))
        parsed = urllib.parse.urlsplit(resolved)
        if parsed.hostname in {"duckduckgo.com", "www.duckduckgo.com"} and parsed.path == "/l/":
            resolved = urllib.parse.parse_qs(parsed.query).get("uddg", [""])[0]
        if resolved:
            candidates.append(resolved)
    pattern = re.compile(
        r"netflix\.com/(?:[a-z]{2}(?:-[a-z]{2})?/)?(?:title|watch)/(\d+)", re.IGNORECASE,
    )
    for candidate in candidates:
        normalized = candidate
        for _ in range(2):
            normalized = urllib.parse.unquote(normalized)
        match = pattern.search(normalized.replace(r"\/", "/"))
        if match:
            return match.group(1)
    if not parser.links and not re.search(r"no-results(?:__message)?", html, re.IGNORECASE):
        _LOGGER.warning("Netflix title lookup returned no recognizable DuckDuckGo result markup")
    _LOGGER.warning("Netflix title lookup returned %d result links without a Netflix title ID", len(candidates))
    raise HomeAssistantError("Netflix title search returned no usable results")


def _netflix_episode_clusters(html: str, title_id: str) -> list[list[int]]:
    """Group sequential Netflix episode video IDs into seasons, following stv's resolver."""
    episode_ids: set[int] = set()
    season_ids: set[int] = set()
    for kind, raw_id in re.findall(
        r'"__typename"\s*:\s*"(Episode|Season|Show)"\s*,\s*"videoId"\s*:\s*(\d+)',
        html,
    ):
        if kind == "Episode":
            episode_ids.add(int(raw_id))
        elif kind == "Season":
            season_ids.add(int(raw_id))
    if episode_ids:
        ids = sorted(episode_ids)
    else:
        raw_ids = {int(value) for value in re.findall(r'"videoId"\s*:\s*(\d+)', html)}
        ids = sorted(raw_ids - season_ids - {int(title_id)})

    clusters: list[list[int]] = []
    current: list[int] = []
    for video_id in ids:
        if current and video_id != current[-1] + 1:
            if len(current) >= 3:
                clusters.append(current)
            current = []
        current.append(video_id)
    if len(current) >= 3:
        clusters.append(current)
    return clusters


async def _async_netflix_episode_id(hass: HomeAssistant, title_id: str, season: int, episode: int) -> str:
    """Resolve a season/episode to its Netflix video ID from the title page."""
    html = await _async_netflix_request(
        hass,
        f"https://www.netflix.com/title/{title_id}",
        headers={"Accept-Language": "en-US,en;q=0.9", "User-Agent": "Mozilla/5.0"},
    )
    seasons = _netflix_episode_clusters(html, title_id)
    if season > len(seasons) or episode > len(seasons[season - 1]):
        raise HomeAssistantError(f"Could not find Netflix S{season}E{episode} for title ID {title_id}")
    return str(seasons[season - 1][episode - 1])


async def _async_netflix_is_movie(hass: HomeAssistant, title_id: str) -> bool:
    """Read Netflix's title metadata to distinguish movies from series before opening a title."""
    try:
        html = await _async_netflix_request(
            hass,
            f"https://www.netflix.com/title/{title_id}",
            headers={"Accept-Language": "en-US,en;q=0.9", "User-Agent": "Mozilla/5.0"},
        )
    except HomeAssistantError:
        _LOGGER.warning("Netflix title type lookup failed; opening the title page")
        return False
    match = re.search(
        rf'"topLevelVideoId"\s*:\s*{re.escape(title_id)}\s*,\s*"type"\s*:\s*"([^"]+)"',
        html,
    )
    return bool(match and match.group(1).casefold() == "movie")


# Netflix title lookup and app-link launch; related: services.yaml and README.ko.md.
async def async_netflix_play(hass: HomeAssistant, call: ServiceCall) -> None:
    """Find a Netflix title and play movies or open the selected series page/episode."""
    query = (call.data.get("query") or "").strip()
    season = call.data.get("season")
    episode = call.data.get("episode")
    entity_id = call.data["entity_id"]
    if not query:
        raise ServiceValidationError("Provide a Netflix title name")
    if (season is None) != (episode is None):
        raise ServiceValidationError("Provide both season and episode, or neither")
    if season is not None and (season < 1 or episode < 1):
        raise ServiceValidationError("Season and episode must be positive numbers")
    if not is_app_link_player(hass, entity_id):
        raise ServiceValidationError("Choose a remote provided by Android TV Remote")

    title_id = await _async_netflix_title_id(hass, query)
    if season is not None:
        content_id = await _async_netflix_episode_id(hass, title_id, season, episode)
        activity = f"https://www.netflix.com/watch/{content_id}?source=30"
    elif await _async_netflix_is_movie(hass, title_id):
        activity = f"https://www.netflix.com/watch/{title_id}?source=30"
    else:
        activity = f"https://www.netflix.com/title/{title_id}?source=30"
    try:
        await hass.services.async_call(
            "remote", "turn_on", {"entity_id": entity_id, "activity": activity}, blocking=True,
        )
    except HomeAssistantError:
        _LOGGER.error("Netflix app-link launch failed for %s", entity_id)
        raise HomeAssistantError("Unable to open Netflix title on the selected TV") from None


# Share Cast identity checks with Assist; related: llm.py and services.yaml.
def is_cast_player(hass: HomeAssistant, entity_id: str) -> bool:
    """Allow only media players registered by the Google Cast integration."""
    if not entity_id.startswith("media_player."):
        return False
    entry = er.async_get(hass).async_get(entity_id)
    return entry is not None and entry.platform == "cast"


# Validate Android TV Remote targets independently; related: llm.py/config_flow.py.
def is_app_link_player(hass: HomeAssistant, entity_id: str) -> bool:
    """Allow only remote entities registered by Android TV Remote."""
    if not entity_id.startswith("remote."):
        return False
    entry = er.async_get(hass).async_get(entity_id)
    return entry is not None and entry.platform == "androidtv_remote"


def playback_mode(hass: HomeAssistant) -> str:
    """Return the configured mode, preserving Cast for older entries."""
    config = hass.data.get(DOMAIN, {})
    if isinstance(config, dict):
        return config.get(CONF_PLAYBACK_MODE, DEFAULT_PLAYBACK_MODE)
    return DEFAULT_PLAYBACK_MODE


def _video_id_from_input(value: str) -> str:
    """Accept an 11-character YouTube video ID or a supported video URL."""
    value = value.strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", value):
        return value
    try:
        parsed = urllib.parse.urlsplit(value)
        host = (parsed.hostname or "").lower()
        if parsed.scheme not in ("http", "https"):
            raise ValueError
        if host == "youtu.be":
            candidate = parsed.path.strip("/").split("/")[0]
        elif host in {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}:
            parts = [part for part in parsed.path.split("/") if part]
            if parsed.path == "/watch":
                candidate = urllib.parse.parse_qs(parsed.query).get("v", [""])[0]
            elif len(parts) == 2 and parts[0] in {"shorts", "embed", "live"}:
                candidate = parts[1]
            else:
                raise ValueError
        else:
            raise ValueError
    except (ValueError, UnicodeError):
        raise ServiceValidationError("Provide a YouTube video URL or 11-character video ID") from None
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", candidate):
        raise ServiceValidationError("Provide a YouTube video URL or 11-character video ID")
    return candidate


# Validate selected playback targets before API requests; related: llm.py/services.yaml.
async def async_search_play(hass: HomeAssistant, call: ServiceCall):
    """Search for or directly select one video and dispatch via configured playback mode."""
    query = (call.data.get("query") or "").strip()
    video = (call.data.get("video") or "").strip()
    if bool(query) == bool(video):
        raise ServiceValidationError("Provide exactly one of a search query or video URL/ID")
    mode = playback_mode(hass)
    app_link_mode = mode in (PLAYBACK_MODE_APP_LINKS + (PLAYBACK_MODE_CAST_FALLBACK,))
    if app_link_mode and not is_app_link_player(hass, call.data["entity_id"]):
        raise ServiceValidationError("Choose a remote provided by Android TV Remote")
    if not app_link_mode and not is_cast_player(hass, call.data["entity_id"]):
        raise ServiceValidationError("Choose a media player provided by Google Cast")
    if video:
        video_id = _video_id_from_input(video)
    else:
        data = await _async_youtube_request(hass, "search", {
            "part": "snippet", "type": "video", "maxResults": 1, "q": query,
        })
        items = data.get("items") or []
        if not items or not items[0].get("id", {}).get("videoId"):
            raise HomeAssistantError("No YouTube video found")
        video_id = items[0]["id"]["videoId"]
    await _async_play_video(
        hass, video_id, call.data["entity_id"], call.data.get("cast_entity_id"),
    )


# Share single-video dispatch between search and local playlist playback; related: services.yaml.
async def _async_play_video(hass: HomeAssistant, video_id: str, entity_id: str, cast_entity_id: Optional[str] = None):
    """Dispatch one known YouTube video using the configured app/Cast mode."""
    mode = playback_mode(hass)
    app_link_mode = mode in (PLAYBACK_MODE_APP_LINKS + (PLAYBACK_MODE_CAST_FALLBACK,))
    valid_target = is_app_link_player(hass, entity_id) if app_link_mode else is_cast_player(hass, entity_id)
    if not valid_target:
        message = "Choose a remote provided by Android TV Remote" if app_link_mode else "Choose a media player provided by Google Cast"
        raise ServiceValidationError(message)
    if app_link_mode:
        activity = f"https://www.youtube.com/watch?v={video_id}"
        if mode in (PLAYBACK_MODE_SMARTTUBE, PLAYBACK_MODE_CAST_FALLBACK):
            activity = f"vnd.youtube.launch://www.youtube.com/watch?v={video_id}"
        try:
            await hass.services.async_call(
                "remote", "turn_on", {
                    "entity_id": entity_id,
                    "activity": activity,
                }, blocking=True,
            )
            return
        except HomeAssistantError:
            if mode not in (PLAYBACK_MODE_APP_LINKS + (PLAYBACK_MODE_CAST_FALLBACK,)):
                raise
            if not cast_entity_id or not is_cast_player(hass, cast_entity_id):
                raise ServiceValidationError(
                    "App-link playback failed; configure a valid Cast fallback entity"
                ) from None
            _LOGGER.warning("Android TV app-link playback failed; trying Google Cast fallback")
            await _async_cast_play(hass, cast_entity_id, video_id)
            return
    await _async_cast_play(hass, entity_id, video_id)


# Keep Cast dispatch shared by the direct and fallback playback paths; related: async_search_play.
async def _async_cast_play(hass: HomeAssistant, entity_id: str, video_id: str, *, enqueue: bool = False) -> None:
    """Send or enqueue a YouTube Cast request for one validated video ID."""
    media_content_id = {"app_name": "youtube", "media_id": video_id}
    if enqueue:
        media_content_id["enqueue"] = True
    await hass.services.async_call(
        "media_player", "play_media", {
            "entity_id": entity_id,
            "media_content_type": "cast",
            "media_content_id": _json_module.dumps(media_content_id),
        }, blocking=True,
    )


# Normalize list/CSV/JSON inputs consistently; related: services.yaml and README.md.
def _normalize_video_ids(value):
    if isinstance(value, str):
        try:
            parsed = _json_module.loads(value)
        except ValueError:
            parsed = value.split(",")
        value = parsed if isinstance(parsed, list) else value.split(",")
    if not isinstance(value, list) or not value:
        raise vol.Invalid("Provide a non-empty video ID list")
    result = []
    for video_id in value:
        if not isinstance(video_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id.strip()):
            raise vol.Invalid("Each YouTube video ID must contain 11 valid characters")
        if video_id.strip() not in result:
            result.append(video_id.strip())
    return result


async def async_playlist_save_service(hass: HomeAssistant, call: ServiceCall):
    """Merge videos into a persistent HA playlist, without modifying YouTube."""
    _require_api_key(hass)
    playlist_id = _sanitize_entity_id(call.data["playlist_id"])
    if not playlist_id:
        raise ServiceValidationError("Playlist ID cannot be empty")
    video_ids = call.data["video_ids"]
    video_infos = []
    for offset in range(0, len(video_ids), 50):
        data = await _async_youtube_request(hass, "videos", {
            "part": "snippet", "id": ",".join(video_ids[offset:offset + 50]),
        })
        metadata = {item["id"]: item.get("snippet", {}) for item in data.get("items", [])}
        for video_id in video_ids[offset:offset + 50]:
            snippet = metadata.get(video_id, {})
            thumbnails = snippet.get("thumbnails", {})
            thumbnail = thumbnails.get("medium", thumbnails.get("default", {}))
            video_infos.append({
                "videoId": video_id, "title": snippet.get("title", ""),
                "channel": snippet.get("channelTitle", ""), "thumbnail": thumbnail.get("url", ""),
            })
    # Persist mutations under a shared lock; related: playlist_store.py/__init__.py.
    playlists = hass.data.get(DOMAIN, {}).get(DATA_PLAYLIST_STORE)
    if playlists is None:
        raise ServiceValidationError("Playlist storage is not configured")
    await playlists.async_merge(playlist_id, video_infos)


async def async_playlist_delete_service(hass: HomeAssistant, call: ServiceCall):
    """Delete a persistent HA playlist, without modifying YouTube."""
    _require_api_key(hass)
    playlist_id = _sanitize_entity_id(call.data["id"])
    if not playlist_id:
        raise ServiceValidationError("Playlist ID cannot be empty")
    # Persist deletion before removing state; related: playlist_store.py.
    playlists = hass.data.get(DOMAIN, {}).get(DATA_PLAYLIST_STORE)
    if playlists is None:
        raise ServiceValidationError("Playlist storage is not configured")
    await playlists.async_delete(playlist_id)


async def async_playlist_list_service(hass: HomeAssistant, call: ServiceCall):
    """Return playlist summaries or one playlist's videos; related: playlist_store.py."""
    playlists = hass.data.get(DOMAIN, {}).get(DATA_PLAYLIST_STORE)
    if playlists is None:
        raise ServiceValidationError("Playlist storage is not configured")
    snapshot = await playlists.async_snapshot()
    playlist_id = call.data.get("playlist_id")
    if playlist_id is None:
        return {"playlists": [
            {"playlist_id": name, "video_count": len(videos)}
            for name, videos in snapshot.items()
        ]}
    playlist_id = _sanitize_entity_id(playlist_id)
    if not playlist_id:
        raise ServiceValidationError("Playlist ID cannot be empty")
    videos = snapshot.get(playlist_id)
    if videos is None:
        raise ServiceValidationError("Playlist not found")
    return {
        "playlist_id": playlist_id,
        "video_count": len(videos),
        "videos": [
            {
                "position": index,
                "video_id": video["videoId"],
                "title": video.get("title", ""),
                "channel": video.get("channel", ""),
                "thumbnail": video.get("thumbnail", ""),
            }
            for index, video in enumerate(videos, 1)
        ],
    }


async def async_playlist_play_service(hass: HomeAssistant, call: ServiceCall):
    """Play all stored videos in order using the YouTube queue; related: playlist_store.py."""
    playlist_id = _sanitize_entity_id(call.data["playlist_id"])
    if not playlist_id:
        raise ServiceValidationError("Playlist ID cannot be empty")
    playlists = hass.data.get(DOMAIN, {}).get(DATA_PLAYLIST_STORE)
    if playlists is None:
        raise ServiceValidationError("Playlist storage is not configured")
    videos = (await playlists.async_snapshot()).get(playlist_id)
    if not videos:
        raise ServiceValidationError("Playlist not found or empty")
    mode = playback_mode(hass)
    entity_id = call.data["entity_id"]
    cast_entity_id = call.data.get("cast_entity_id")
    app_link_mode = mode in (PLAYBACK_MODE_APP_LINKS + (PLAYBACK_MODE_CAST_FALLBACK,))
    if app_link_mode and len(videos) > 1 and not cast_entity_id:
        raise ServiceValidationError("Choose a Google Cast entity to queue the remaining videos")
    if cast_entity_id and not is_cast_player(hass, cast_entity_id):
        raise ServiceValidationError("Choose a Google Cast player")
    await _async_play_video(hass, videos[0]["videoId"], entity_id, cast_entity_id)
    queue_entity = cast_entity_id if app_link_mode else entity_id
    for video in videos[1:]:
        await _async_cast_play(hass, queue_entity, video["videoId"], enqueue=True)


async def async_setup_services(hass: HomeAssistant):
    """Register validated actions once; related: services.yaml/config_flow.py."""
    async def _search_play(call: ServiceCall):
        await async_search_play(hass, call)

    async def _netflix_play(call: ServiceCall):
        await async_netflix_play(hass, call)

    async def _playlist_save_service(call: ServiceCall):
        await async_playlist_save_service(hass, call)

    async def _playlist_delete_service(call: ServiceCall):
        await async_playlist_delete_service(hass, call)

    async def _playlist_list_service(call: ServiceCall):
        return await async_playlist_list_service(hass, call)

    async def _playlist_play_service(call: ServiceCall):
        await async_playlist_play_service(hass, call)

    actions = {
        "youtube_search_play": (_search_play, vol.Schema({
            vol.Optional("query"): cv.string,
            vol.Optional("video"): cv.string,
        vol.Required("entity_id"): cv.entity_id,
            vol.Optional("cast_entity_id"): vol.All(cv.entity_id, vol.Match(r"^media_player\.")),
        })),
        "netflix_play": (_netflix_play, vol.Schema({
            vol.Required("query"): cv.string,
            vol.Required("entity_id"): vol.All(cv.entity_id, vol.Match(r"^remote\.")),
            vol.Optional("season"): vol.All(vol.Coerce(int), vol.Range(min=1)),
            vol.Optional("episode"): vol.All(vol.Coerce(int), vol.Range(min=1)),
        })),
        "youtube_playlist_save": (_playlist_save_service, vol.Schema({
            vol.Required("playlist_id"): cv.string,
            vol.Required("video_ids"): _normalize_video_ids,
        })),
        "youtube_playlist_delete": (_playlist_delete_service, vol.Schema({vol.Required("id"): cv.string})),
        "youtube_playlist_list": (_playlist_list_service, vol.Schema({
            vol.Optional("playlist_id"): cv.string,
        })),
        "youtube_playlist_play": (_playlist_play_service, vol.Schema({
            vol.Required("playlist_id"): cv.string,
            vol.Required("entity_id"): cv.entity_id,
            vol.Optional("cast_entity_id"): vol.All(cv.entity_id, vol.Match(r"^media_player\.")),
        })),
    }
    for name, (handler, schema) in actions.items():
        if not hass.services.has_service(DOMAIN, name):
            hass.services.async_register(
                DOMAIN, name, handler, schema=schema,
                **({"supports_response": SupportsResponse.ONLY} if name == "youtube_playlist_list" else {}),
            )


async def async_unload_services(hass: HomeAssistant):
    """Unregister legacy service functions."""
    try:
        hass.services.async_remove(DOMAIN, "youtube_search_play")
        hass.services.async_remove(DOMAIN, "netflix_play")
        hass.services.async_remove(DOMAIN, "youtube_playlist_save")
        hass.services.async_remove(DOMAIN, "youtube_playlist_delete")
        hass.services.async_remove(DOMAIN, "youtube_playlist_list")
        hass.services.async_remove(DOMAIN, "youtube_playlist_play")
    except Exception as err:
        _LOGGER.error("Assist Google TV services unload failed: %s", err, exc_info=True)
