# Changelog

Notable changes to Assist Google TV are documented here.

## [1.1.0] - 2026-11-23

- Add **ADB-only TV input switching** with input discovery, verification of the active input, and a configurable source for live TV.
- Add **ADB-only TV standby and full shutdown** as separate Assist commands.
- Add a Google TV Assist provider to launch configured apps and return to the home screen through Android TV Remote or ADB. ADB can also stop configured apps.
- Guide TV and app selection during setup and reconfiguration. Detect ADB apps and suggest YouTube and Netflix app links for Android TV Remote.
- Play YouTube playlist URLs, list and play saved playlists in order, and target Google Cast directly in any playback mode.
- Search Netflix within a configurable region and play episodes by season, cumulative series number, or the latest episode listed.
- Dismiss the TV screensaver before playback and configured app launches.
- Correct Home Assistant entity IDs for saved playlists while preserving the existing playlist data.
- Shorten Assist tool prompts and list shared Google Cast fallback targets once.
- Add bilingual GitHub issue forms for bug reports and feature requests.

## [1.0.0] - 2026-10-26

- Publish Assist Google TV as a fresh Home Assistant integration version.
- Rewrite the English and Korean README guides for the current actions, playback options, and Assist providers.
- Keep YouTube playlist storage and state IDs available to existing data.

## YouTube Content Search 1.1.0 - 2026-10-18

- Play a specific YouTube video directly from a supported video URL or 11-character video ID in actions and Assist tools.
- Align Assist Cast-player discovery with the Cast integration criterion used by the action selector.
- Add English and Korean README files, with English as the default README.
- Add a GitHub Actions workflow for HACS repository validation.

## YouTube Content Search 1.0.1 - 2026-10-17

- Add a selectable YouTube Content Search provider and YouTube search/play tool for compatible Assist conversation agents.
- Restrict playback targets to registered Google Cast media players.
- Persist Home Assistant local playlists and restore them after restarts.
- Improve YouTube API error reporting while keeping API keys and raw response details out of user-facing errors.
- Keep the integration service-only; the sidebar panel and HTTP search endpoints are inactive.
