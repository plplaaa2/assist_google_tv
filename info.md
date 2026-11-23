# Assist Google TV 1.1.0

Control Google TV with Home Assistant Assist. Search and play YouTube videos, open Netflix titles and episodes, and manage local YouTube playlists.

## Features

- Separate YouTube and Netflix Assist tool providers.
- YouTube playback from search terms or a direct video URL/ID.
- Netflix movie, series, and episode links through Android TV Remote.
- Local playlists that persist across Home Assistant restarts.
- ADB-only TV input switching, standby, and full shutdown.

## Requirements

- Home Assistant and a conversation agent that supports tool calls.
- YouTube Data API v3 key for YouTube search and playlist actions; Netflix does not need the key.
- Google Cast and/or Android TV Remote, depending on the selected playback mode.
- Android Debug Bridge (ADB) for TV input switching and power control.

See [README](README.md) for installation and examples.
