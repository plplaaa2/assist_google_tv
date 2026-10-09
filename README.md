# YouTube Content Search for Home Assistant

A custom integration for [Home Assistant](https://www.home-assistant.io/) that allows you to search for YouTube videos, create playlists, and cast them directly to supported media players (Chromecast, Nest Hub, smart TVs with Cast support) using a web UI.

---

## System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Home Assistant                                │
│                                                                       │
│  ┌──────────────────┐    Service Call      ┌───────────────────┐   │
│  │  Web UI Panel     │ ◄───── REST API ──► │  HTTP Endpoints   │   │
│  │ (Sidebar)         │                      │                   │   │
│  │                  │  POST /youtube-search │  GET/POST/DELETE   │   │
│  │  Search Videos    │  GET  /playlist-     │  - /youtube-search │   │
│  │  Create Playlist  │     detail/{id}      │  - /playlist-      │   │
│  │  Save/Delete VL   │                      │     save           │   │
│  └──────────────────┘    Service Call      │  - /playlist-      │   │
│                                             │     delete         │   │
└──────────────┬──────────────────────────┬───┴──────────────────────┘
               │                          │
               ▼                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│  custom_components/youtube_content_search/                           │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │  __init__.py             │  options_flow.py                     ││
│  │  - Integration Setup     │  - API Key Configuration UI           ││
│  │    & Migration           │  (Store pattern)                      ││
│  └───────────┬──────────────┘                                       ││
│              │                                                        ││
│  ┌───────────▼──────────────┐                                       ││
│  │  services.py             │                                       ││
│  │                          │                                       ││
│  │  ┌──────────────────────┤                                       ││
│  │  │ REST API Handlers    │                                       ││
│  │  ├─ async_handle_       │                                       ││
│  │  │   youtube_search     │                                       ││
│  │  ├─ async_handle_       │                                       ││
│  │  │   playlist_detail    │                                       ││
│  │  ├─ async_handle_       │                                       ││
│  │  │   playlist_save      │                                       ││
│  │  └─ async_handle_       │                                       ││
│  │     playlist_delete     │                                       ││
│  │                          │                                       ││
│  │  ┌──────────────────────┤                                       ││
│  │  │ Service Functions    │                                       ││
│  │  ├─ async_search_play   │                                       ││
│  │  ├─ async_playlist_     │                                       ││
│  │  │   save_service       │                                       ││
│  │  └─ async_playlist_     │                                       ││
│  │      delete_service     │                                       ││
│  │                          │                                       ││
│  │  ┌──────────────────────┤                                       ││
│  │  │ Helpers              │                                       ││
│  │  ├─ _get_api_key()      │                                       ││
│  │  └─ _sanitize_entity_id()│                                      ││
│  └───────────┬──────────────┘                                       ││
└──────────────┼───────────────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        YouTube Data API v3                           │
│                                                                       │
│  ──────────────────────────────────────────────────────              │
│         GET /youtube/v3/search                                       │
│         GET /youtube/v3/playlists                                    │
│         POST /youtube/v3/playlistItems                               │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Features

- 🔍 **YouTube Search**: Search for videos using the YouTube Data API v3
- 📋 **Playlist Management**: Create, save, and delete playlists
- 🖥️ **Web UI Panel**: Built-in sidebar panel with a modern interface
- 🎯 **Cast Support**: Cast content directly to Chromecast, Nest Hub, or smart TVs
- 🔒 **Secure API Key Storage**: Using Home Assistant's `Store` pattern for safe key management
- ⚡ **Service Integration**: Works seamlessly with HA scripts and automations

---

## Requirements

| Requirement | Description |
|-------------|-------------|
| Python 3.9+ | Required by Home Assistant |
| aiohttp | HTTP library dependency (declared in `requirements`) |
| YouTube Data API Key | Free key from [Google Cloud Console](https://console.cloud.google.com/) with YouTube Data API v3 enabled |

---

## Installation

### Via HACS

1. Open **HACS** → **Integrations** → **⋮** → **Custom repositories**
2. Add repository: `plplaaa2/youtube_content_search` (URL) and `youtube_content_search` (manifest path)
3. Click **Add**, then click the integration in **Installed** to install

### Manual Installation

1. Copy the entire `youtube_content_search-main/` directory to your Home Assistant configuration's `custom_components/` folder
2. Restart Home Assistant
3. Go to **Settings → Devices & Services** and enable YouTube Content Search

---

## Configuration

After installation, configure your API key:

1. Go to **Settings → Devices & Services → YouTube Content Search**
2. Click the **⋮** (three dots) next to the integration
3. Select **Options**
4. Enter your **YouTube Data API Key** and save

### Where to get an API Key

1. Visit [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project or select an existing one
3. Enable **YouTube Data API v3**
4. Go to **Credentials** → **Create Credentials** → **API Key**
5. Copy and paste the key into the integration settings

---

## Usage

### Web UI (Recommended)

Once configured, access the web panel via:

- Go to **Settings → Sidebar** or use the Home Assistant mobile app
- Find **YouTube Content Search** in the sidebar
- Use the search bar to find videos and playlists
- Create and manage playlists directly from the UI

### Service Calls (Automation / Script)

You can also trigger actions via Home Assistant services:

#### Search & Cast a Video
```yaml
service: youtube_content_search.search_play
data:
  query: "Python tutorial"
  entity_id: media_player.living_room_tv
```

#### Save Videos to Playlist
```yaml
service: youtube_content_search.playlist_save
data:
  video_ids: ["dQw4w9WgXcQ", "jNQXAC9IVRw"]
  playlist_id: "PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf"
```

#### Delete Playlist
```yaml
service: youtube_content_search.playlist_delete
data:
  id: "PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf"
```

---

## Project Structure

```
youtube_content_search-main/
│
├── hacs.json                          # HACS metadata (name, manifest_version, etc.)
├── icon.png                           # Brand icon (256×256px)
├── logo.png                           # Brand logo
├── LICENSE                            # License file
├── README.md                          # This file (user guide + installation)
└── custom_components/
    └── youtube_content_search/        # Custom Component directory
        │
        ├── __init__.py                # Main setup entry point
        │                               - HTTP route registration
        │                               - Service registration
        │                               - Storage initialization & migration
        ├── const.py                   # Constants (DOMAIN, CONF_API_KEY, PANEL config)
        ├── services.py                # Core implementation
        │                               - REST API handlers (/youtube-search, /playlist-*)
        │                               - Service functions (search_play, playlist_save/delete)
        │                               - Helper functions (_get_api_key, _sanitize_entity_id)
        ├── options_flow.py            # API key configuration UI via HA options flow
        └── manifest.json              # Integration manifest file
```

---

## Security Improvements

### Entity ID Sanitization
All playlist IDs are sanitized before being used as Home Assistant entity IDs. Special characters (hyphens, underscores, etc.) are removed to prevent security issues:

```python
# Input: "PL-abc123" → Output: "pl_abc123"
sanitized = "".join(c.lower() for c in playlist_id if c.isalnum() or c in "_-.").strip()
```

### Secure API Key Storage
API keys are stored using HA's `Store` pattern, which encrypts sensitive data at rest. The key is also cached in `hass.data` for immediate service access.

---

## Support & Contribution

- [GitHub Repository](https://github.com/plplaaa2/youtube_content_search)
- [Open Issues](https://github.com/plplaaa2/youtube_content_search/issues)

---

<div align="center">
  <a href="https://ko-fi.com/plplaaa2"><img src="https://ko-fi.com/img/githubbutton_sm.svg" alt="Ko-fi Support"></a>
</div>

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/plplaaa2)

---

*Made with ❤️ for the Home Assistant community*