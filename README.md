# Assist Google TV

[English](README.md) | [한국어](README.ko.md)

[Changelog](CHANGELOG.md)

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)
![version](https://img.shields.io/badge/version-v1.1.0-blue.svg?style=for-the-badge)
[![kofi](https://img.shields.io/badge/Ko--fi-Support%20Me-F16061?style=for-the-badge&logo=ko-fi)](https://ko-fi.com/plplaaa2)

Use Assist voice commands to search and play YouTube videos or open Netflix titles and episodes through Home Assistant actions and Android TV app links.
The sidebar panel and HTTP search endpoints are currently inactive.

## Installation and setup

### Automatic installation (recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=plplaaa2&repository=https%3A%2F%2Fgithub.com%2Fplplaaa2%2Fassist_google_tv&category=integration)

Click the badge above and install the integration.

### Manual installation

Copy only the `custom_components/assist_google_tv` folder to `/config/custom_components/assist_google_tv` in Home Assistant.

**Migration note:** This release changes the Home Assistant integration domain. Remove the old YouTube Content Search config entry and add Assist Google TV again, then enter the YouTube API key. Update existing actions from `youtube_content_search.*` to `assist_google_tv.*` and select the new Assist providers again. Saved playlist data remains in `.storage/youtube_content_search.playlists` and retains its `youtube_content_search._playlist_*` state IDs.

### Configure

1. Enable YouTube Data API v3 in Google Cloud and prepare an API key.
2. Set up Google Cast and/or Android TV Remote. Android TV app modes require an Android TV Remote `remote` entity.
3. Restart Home Assistant, then add Assist Google TV from **Settings → Devices & services → Add integration**.
4. Enter the API key and playback mode in the integration configuration. Option changes apply to subsequent actions.

The key is stored in the Home Assistant config entry; this integration does not provide additional encryption. You do not need to put the actual key in automation YAML.

## Search and play

Call the action from **Developer tools → Actions**, an automation, or a script. It plays the first matching video; playlist search is not supported. Select official YouTube app to Cast fallback, SmartTube to Cast fallback, or Google Cast only in the integration options. App-link modes request Cast playback if the remote action returns an error.

Android TV app modes send a video deep link to an Android TV Remote `remote` entity and use `cast_entity_id` for the Google Cast `media_player` fallback. SmartTube mode uses its `vnd.youtube.launch` link. Deep-link handling can vary by device and app version.

```yaml
action: assist_google_tv.search_play
data:
  query: "IU live"
  entity_id: media_player.living_room_tv # use remote.living_room_tv for app-link mode
```

To play a specific video without searching, use `video` with a YouTube video URL or 11-character video ID instead of `query`. Provide exactly one of `query` or `video`.

```yaml
action: assist_google_tv.search_play
data:
  video: "https://youtu.be/dQw4w9WgXcQ"
  entity_id: media_player.living_room_tv # use remote.living_room_tv for app-link mode
```

## Open Netflix titles

The `netflix_play` action searches the web for a Netflix title ID and opens it through Android TV Remote. Provide both season and episode to open a specific episode.

```yaml
action: assist_google_tv.netflix_play
data:
  query: "Frieren: Beyond Journey's End"
  season: 2
  episode: 8
  entity_id: remote.living_room_tv
```

Omit season and episode to play a movie directly or open a series title page. The integration reads Netflix title metadata to distinguish movies from series; if that lookup fails, it safely opens the title page. Netflix lookup runs its own DuckDuckGo HTML search client, based on Assist Web Search's request, challenge detection, browser-fingerprint retry and structured result parsing. It does not require Assist Web Search to be installed. Search challenges or markup changes are reported as lookup errors. If search returns multiple matches, the first Netflix link is used. Episode IDs are extracted from the Netflix page and grouped into seasons by consecutive ID ranges.

## Connect the Assist tool

Install the updated integration and restart Home Assistant. You need an LLM conversation agent that supports tool calls.

1. In **Settings → Voice assistants**, expose both the Android TV Remote and Cast player to Assist.
2. In the conversation agent settings, select **Assist Google TV (YouTube)** and/or **Assist Google TV (Netflix)** under **Tool providers** or **Control Home Assistant / LLM API**. They are registered as separate providers.
3. Select only YouTube for YouTube playback, only Netflix for Netflix playback, or both. Neither provider's tools are added automatically to the built-in **Assist** API.
4. Ask the voice assistant using that agent, for example, “Play IU live on the living room TV.”

The tool is named `assist_google_tv__search_play`. It accepts either `query` (search terms) or `video` (a YouTube video URL or ID), plus `entity_id`. Specify only one of `query` and `video`.

Assist receives targets for the selected playback mode and checks integration ownership again before calling the action. App-link modes require both the Android TV Remote and Cast player.

The Netflix tool is named `assist_google_tv__netflix_play`. It accepts a title `query`, an Android TV Remote `entity_id`, and optional `season` and `episode` values. It is independent of the YouTube tool and does not use the YouTube API key.

A successful response means the playback request was sent; it does not confirm that video or audio actually started. Saving and deleting local playlists are not available as Assist tools. API keys and raw backend errors are not sent to the LLM.

Settings names vary by Home Assistant version and conversation agent. The built-in conversation agent does not call this LLM tool. Windows mock tests cover provider setup and reload, API tool discovery, permissions, and error handling; actual Home Assistant listing and playback require separate verification.

If the provider is missing, check that the integration is installed and loaded after restarting Home Assistant, then reopen the conversation agent settings.

Official interface: [Home Assistant LLM API and tool contribution](https://developers.home-assistant.io/docs/core/llm/).

## Home Assistant local playlists

Playlists are stored in Home Assistant and do not modify your YouTube account. Video metadata is saved locally and restored after Home Assistant restarts or the integration reloads. There is no action to play an entire playlist. Playlist names are normalized for entity IDs, and duplicate videos are merged.

The storage file is `.storage/youtube_content_search.playlists` in the Home Assistant config directory. Additions and deletions are reflected in Home Assistant only after storage succeeds; deleted playlists stay deleted after a restart. Include this file in backups and do not edit it directly. The file is retained if you remove the integration entry, and playlists are restored when you configure it again.

If legacy temporary playlist states exist and there is no storage file, the first initialization imports them. Temporary states already lost after a Home Assistant restart cannot be recovered by updating the integration. A playlist management UI is not currently provided; use the actions and **Developer tools → States**.

```yaml
action: assist_google_tv.playlist_save
data:
  playlist_id: "my_music"
  video_ids:
    - "dQw4w9WgXcQ"
    - "jNQXAC9IVRw"
```

`video_ids` accepts a YAML list, comma-separated string, or JSON array string. To inspect a playlist, open `youtube_content_search._playlist_my_music` in **Developer tools → States** and check its `data` attribute.

```yaml
action: assist_google_tv.playlist_delete
data:
  id: "my_music"
```

## Troubleshooting and removal

API errors and empty search results are reported as action errors. Check API usage and permissions in Google Cloud. API errors show the HTTP status and allowlisted reason codes; keys, request URLs, and raw response text are not displayed.

For example, `HTTP 400 (reason: invalidFilters)` indicates an invalid request filter, while `API_KEY_INVALID` points to the key. Check that the API is enabled for `SERVICE_DISABLED` and review quota usage for `quotaExceeded`. Unknown codes and non-JSON responses are shown as `reason: UNKNOWN`.

Restart Home Assistant after updating files. Removing the integration entry clears runtime credentials. To remove the code, uninstall it through HACS or delete the manual installation folder, then restart Home Assistant. Frontend files and the unconnected `options_flow.py` are retained; the active options flow is in `config_flow.py`.

## Development checks

On Windows, install `aiohttp` and `voluptuous` in Python, then run:

```powershell
python -B -m unittest discover -s tests -v
```

Tests mock Home Assistant interfaces and use temporary files to verify playlist restoration. Actual Home Assistant Store behavior, configuration loading, API authentication, and TV playback require separate verification.

The HACS validation GitHub Action runs on pushes, pull requests, daily, and on manual dispatch. It validates this repository as an integration.

## Official references

- [Home Assistant manifest](https://developers.home-assistant.io/docs/creating_integration_manifest/)
- [Home Assistant custom integration translations](https://developers.home-assistant.io/docs/internationalization/custom_integration/)
- [Google Cast YouTube playback](https://www.home-assistant.io/integrations/cast/#youtube)
- [YouTube video metadata](https://developers.google.com/youtube/v3/docs/videos/list)
- [HACS publishing requirements](https://www.hacs.xyz/docs/publish/integration/)
