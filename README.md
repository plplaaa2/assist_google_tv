# Assist Google TV

Control Google TV with Home Assistant Assist. Search and play YouTube videos, open Netflix titles and episodes, and manage local YouTube playlists.

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)
![Version](https://img.shields.io/badge/version-v1.0.0-blue.svg?style=for-the-badge)
[![Ko-fi](https://img.shields.io/badge/Ko--fi-Support%20Me-F16061?style=for-the-badge&logo=ko-fi)](https://ko-fi.com/plplaaa2)

[한국어 안내](README.ko.md)

## Install

### HACS

[![Open this repository in Home Assistant](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=plplaaa2&repository=https%3A%2F%2Fgithub.com%2Fplplaaa2%2Fassist_google_tv&category=integration)

Install the integration, restart Home Assistant, then add **Assist Google TV** from **Settings → Devices & services → Add integration**.

### Manual

Copy `custom_components/assist_google_tv` to `/config/custom_components/assist_google_tv`, restart Home Assistant, and add **Assist Google TV**.

## Configure

Set up Google Cast and/or Android TV Remote in Home Assistant. In the integration setup, enter a YouTube Data API v3 key if you use YouTube search or playlist actions, then choose a playback mode:

- **SmartTube → Cast fallback** (default)
- **Official YouTube app → Cast fallback**
- **Google Cast only**

App-link modes need an Android TV Remote `remote` entity and a Google Cast `media_player` for fallback. Cast-only mode uses a Google Cast `media_player`. Netflix actions use Android TV Remote and do not require a YouTube API key.

The API key is stored in the Home Assistant config entry. Keep it out of automation YAML.

## Actions

### Search and play YouTube

Use a search query or a YouTube video URL/ID. Supply exactly one of `query` and `video`.

```yaml
action: assist_google_tv.youtube_search_play
data:
  query: "IU live"
  entity_id: remote.living_room_tv
  cast_entity_id: media_player.living_room_tv
```

For a specific video:

```yaml
action: assist_google_tv.youtube_search_play
data:
  video: "https://youtu.be/dQw4w9WgXcQ"
  entity_id: remote.living_room_tv
  cast_entity_id: media_player.living_room_tv
```

Use a `media_player` as `entity_id` in Cast-only mode. `cast_entity_id` is only needed for app-link fallback.

### Open Netflix titles

Provide a title and Android TV Remote entity. Add both `season` and `episode` to open a specific episode. Without them, movies open directly and series open their title page.

```yaml
action: assist_google_tv.netflix_play
data:
  query: "Frieren: Beyond Journey's End"
  season: 2
  episode: 8
  entity_id: remote.living_room_tv
```

### Save and delete playlists

Playlists are stored in Home Assistant and do not modify your YouTube account.

```yaml
action: assist_google_tv.youtube_playlist_save
data:
  playlist_id: "my_music"
  video_ids:
    - "dQw4w9WgXcQ"
    - "jNQXAC9IVRw"
```

`video_ids` also accepts a comma-separated string or a JSON array string.

```yaml
action: assist_google_tv.youtube_playlist_delete
data:
  id: "my_music"
```

List saved playlists and their video counts. Set `playlist_id` to return video titles, channels, and positions. Automations can capture the response in a variable:

```yaml
action: assist_google_tv.youtube_playlist_list
data:
  playlist_id: "my_music"
response_variable: playlist
```

Play every saved video in order:

```yaml
action: assist_google_tv.youtube_playlist_play
data:
  playlist_id: "my_music"
  entity_id: remote.living_room_tv
  cast_entity_id: media_player.living_room_tv
```

In app-link modes, the first video opens through Android TV Remote and the remaining videos are added to the Cast queue for the same TV. In Cast-only mode, set `entity_id` to the Google Cast player.

## Use with Assist

1. Expose the target Android TV Remote and/or Google Cast entities to Assist.
2. In integration options, configure the app-launch control method (Remote or ADB), TV entity ID, and app JSON list. Each item uses `{"name":"YouTube","launch":"https://www.youtube.com"}`. Remote uses an activity/deep link; ADB uses the app package ID.
3. In a compatible conversation agent's **Tool providers** or **LLM API** settings, select **Assist Google TV (YouTube)**, **Assist Google TV (Netflix)**, **Assist Google TV (App Launch)**, or any combination.
4. Ask the voice assistant to play a YouTube video, open a Netflix title, or launch a configured app.

The YouTube provider offers `assist_google_tv__youtube_search_play`. The separate Netflix provider offers `assist_google_tv__netflix_play` and works without a YouTube API key. The app provider offers `assist_google_tv__open_app`; ADB mode also provides `assist_google_tv__stop_app`. Android TV Remote does not support app stopping. Playlist actions are available in Home Assistant, not as Assist tools.

A successful response confirms that Home Assistant sent the playback request; it does not confirm that video or audio started.

## Development

Run the mock tests with:

```powershell
python -B -m unittest discover -s tests -v
python -B validate_syntax.py
```

## Credits and license

Maintained by [plplaaa2](https://github.com/plplaaa2). Developed with assistance from [OpenAI Codex](https://openai.com/codex/).

The DuckDuckGo HTML request format, result parsing approach, and browser-fingerprint fallback in the Netflix title lookup are adapted from or inspired by [Nick Clyde's `duckduckgo-mcp-server`](https://github.com/nickclyde/duckduckgo-mcp-server), available under the MIT License. Its MCP runtime is not included. The required copyright and permission notice is preserved in [`THIRD_PARTY_NOTICES.md`](custom_components/assist_google_tv/THIRD_PARTY_NOTICES.md). The remaining project code is licensed under this repository's [MIT License](LICENSE).

\n
