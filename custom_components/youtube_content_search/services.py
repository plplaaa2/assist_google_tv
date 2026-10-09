"""YouTube Content Search - 서비스 및 HTTP 처리 모듈."""

import asyncio
import json as _json_module
import aiohttp
import aiohttp.web
import logging
import urllib.parse
from typing import Any, Optional
from homeassistant.core import HomeAssistant, ServiceCall
from .const import DOMAIN, CONF_API_KEY

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
    sanitized = "".join(c.lower() for c in playlist_id if c.isalnum() or c in "_-.").strip()

    import re
    sanitized = re.sub(r'[^a-z0-9_.\-]', '_', sanitized)

    return sanitized if sanitized else None


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
        entity_id = f"youtube_content_search._playlist_{sanitized_playlist_id}"

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
        entity_id = f"youtube_content_search._playlist_{sanitized_playlist_id}"
        hass.states.async_remove(entity_id)
        return aiohttp.web.json_response({"success": True, "message": f"Playlist '{playlist_id}' deleted"})

    except Exception as e:
        _LOGGER.exception("Error deleting playlist %s: %s", playlist_id, e)
        return aiohttp.web.json_response({"error": str(e)}, status=500)


# ──────────────────────────── Service Functions (Cast Playback / Legacy Mode) ────────────

async def async_search_play(hass: HomeAssistant, call: ServiceCall):
    """Handle search_play service call - searches YouTube and starts Cast playback.

    HA calls this as: await target(service_call, hass_instance)
    So the second parameter is the HomeAssistant instance.
    """
    api_key = _get_api_key(hass)
    query = call.data.get("query")
    entity_id = call.data.get("entity_id")

    if not query or not entity_id:
        _LOGGER.error("Missing 'query' or 'entity_id' for search_play service.")
        return None

    encoded_query = urllib.parse.quote(query)
    url = (
        f"https://www.googleapis.com/youtube/v3/search?"
        f"part=snippet&type=video,playlist&maxResults=1&q={encoded_query}&key={api_key}"
    )

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    _LOGGER.error("YouTube API error: %s", resp.status)
                    return None
                data = await resp.json()

    except Exception as e:
        _LOGGER.exception("Error during YouTube search response fetch: %s", e)
        return None

    items = (data.get("items") or [])
    if len(items) == 0:
        _LOGGER.warning("No YouTube results found for query: %s", query)
        return None

    item = items[0]
    id_info = item.get("id", {})

    media_id = None

    if "videoId" in id_info:
        media_id = id_info["videoId"]
    elif "playlistId" in id_info:
        media_id = id_info["playlistId"]
    else:
        _LOGGER.warning("No valid videoId or playlistId found in search results")
        return None

    cast_payload = {
        "app_name": "youtube",
        "media_id": media_id
    }

    try:
        await hass.services.async_call(
            "media_player",
            "play_media",
            {
                "entity_id": entity_id,
                "media_content_type": "cast",
                "media_content_id": json.dumps(cast_payload)
            },
        )
    except Exception as e:
        _LOGGER.exception("Error calling play_media service: %s", e)


async def async_playlist_save_service(hass: HomeAssistant, call: ServiceCall):
    """플레이리스트에 동영상 추가 (Service 기반 - Cast/legacy 모드).

    HA calls this as: await target(service_call, hass_instance)
    """
    api_key = _get_api_key(hass)
    video_ids_str = call.data.get("video_ids")
    playlist_id = call.data.get("playlist_id")

    if not video_ids_str or not playlist_id:
        _LOGGER.error("Missing required parameters for playlist_save service")
        return None

    # video_ids를 쉼표로 구분하여 파싱 (또는 JSON 배열)
    if isinstance(video_ids_str, list):
        video_ids = [str(v).strip() for v in video_ids_str]
    else:
        try:
            video_ids = _json_module.loads(video_ids_str)
        except (_json_module.JSONDecodeError, TypeError):
            # 쉼표 구분으로 파싱 시도
            video_ids = [v.strip() for v in str(video_ids_str).split(',') if v.strip()]

    if not video_ids:
        _LOGGER.error("No valid video IDs provided")
        return None

    sanitized_playlist_id = _sanitize_entity_id(str(playlist_id))
    if not sanitized_playlist_id:
        _LOGGER.error("Invalid playlist_id for playlist_save service: %s", playlist_id)
        return None

    try:
        entity_id = f"youtube_content_search._playlist_{sanitized_playlist_id}"

        states = hass.states.async_all()
        playlist_state = None
        for s in states:
            if s.entity_id == entity_id:
                playlist_state = s
                break

        # YouTube API를 통해 해당 영상의 스니펫 정보 가져오기 (다중 요청 병렬)
        async def _fetch_video_info(vid):
            try:
                async with aiohttp.ClientSession() as session:
                    url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&id={vid}&type=video&key={api_key}"
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            items = (data.get("items") or [])[:1]
                            for item in items:
                                thm = ""
                                tbs = item.get("snippet", {}).get("thumbnails", {})
                                if "medium" in tbs:
                                    thm = tbs["medium"].get("url") or tbs.get("default", {}).get("url")
                                return {
                                    "videoId": vid,
                                    "title": item.get("snippet", {}).get("title"),
                                    "channel": item.get("snippet", {}).get("channelTitle"),
                                    "thumbnail": thm,
                                }
            except Exception as e:
                _LOGGER.debug("Error fetching video %s info: %s", vid, e)

            return {"videoId": vid, "title": "", "channel": "", "thumbnail": ""}

        video_infos = await asyncio.gather(*[
            _fetch_video_info(v) for v in video_ids
        ])

        # 새 데이터 준비 (중복 제거 + 기존 유지)
        new_videos = []
        existing_vids = set()
        if playlist_state:
            try:
                existing_attr = _json_module.loads(playlist_state.attributes.get('data', '[]'))
                for v in (existing_attr or []):
                    vid_key = v['videoId'] if isinstance(v, dict) else str(v).split(',')[0].strip()
                    existing_vids.add(vid_key)
                    new_videos.append(v)
            except Exception as e:
                _LOGGER.error("Error parsing playlist %s: %s", entity_id, e)

        for info in video_infos:
            if info['videoId'] not in existing_vids:
                new_videos.append(info)
                existing_vids.add(info['videoId'])

        # 상태 업데이트 (이벤트 발생 → HA에서 UI 갱신)
        hass.states.async_set(entity_id, 'on', {'data': _json_module.dumps(new_videos)})

    except Exception as e:
        _LOGGER.exception("Error during playlist_save service: %s", e)


async def async_playlist_delete_service(hass: HomeAssistant, call: ServiceCall):
    """플레이리스트 삭제 (Service 기반 - Cast/legacy 모드).

    HA calls this as: await target(service_call, hass_instance)
    """
    playlist_id = call.data.get("id")

    if not playlist_id:
        _LOGGER.error("Missing required parameters for playlist_delete service")
        return None

    sanitized_playlist_id = _sanitize_entity_id(str(playlist_id))
    if not sanitized_playlist_id:
        _LOGGER.error("Invalid playlist_id for playlist_delete service: %s", playlist_id)
        return None

    try:
        entity_id = f"youtube_content_search._playlist_{sanitized_playlist_id}"
        hass.states.async_remove(entity_id)
    except Exception as e:
        _LOGGER.warning("Failed to delete state %s: %s", entity_id, e)


# ──────────────────────────── Setup / Unregister Helpers ───────────────────

async def async_setup_services(hass: HomeAssistant):
    """Register legacy service functions for Cast playback."""

    async def _search_play(call: ServiceCall):
        await async_search_play(hass, call)

    async def _playlist_save_service(call: ServiceCall):
        await async_playlist_save_service(hass, call)

    async def _playlist_delete_service(call: ServiceCall):
        await async_playlist_delete_service(hass, call)

    try:
        hass.services.async_register(DOMAIN, "search_play", _search_play)
        if not hass.services.has_service(DOMAIN, "playlist_save"):
            hass.services.async_register(DOMAIN, "playlist_save", _playlist_save_service)
        if not hass.services.has_service(DOMAIN, "playlist_delete"):
            hass.services.async_register(DOMAIN, "playlist_delete", _playlist_delete_service)

    except Exception as err:
        _LOGGER.error("YouTube Content Search services registration failed: %s", err, exc_info=True)


async def async_unload_services(hass: HomeAssistant):
    """Unregister legacy service functions."""
    try:
        hass.services.async_remove(DOMAIN, "search_play")
        hass.services.async_remove(DOMAIN, "playlist_save")
        hass.services.async_remove(DOMAIN, "playlist_delete")
    except Exception as err:
        _LOGGER.error("YouTube Content Search services unload failed: %s", err, exc_info=True)