# Changelog

Notable changes to Assist Google TV are documented here.

## [1.1.8-dev] - 2026-10-26

- Rename the custom integration folder and domain to `assist_google_tv`.
- Update action and Assist tool IDs to the new domain; existing automations and selected providers must be updated.
- Preserve the previous playlist storage key and playlist state IDs.
- Document the required config-entry and API-key reconfiguration after upgrading.

## [1.1.0] - 2026-10-18

- Play a specific YouTube video directly from a supported video URL or 11-character video ID in actions and Assist tools.
- Align Assist Cast-player discovery with the Cast integration criterion used by the action selector.
- Add English and Korean README files, with English as the default README.
- Add a GitHub Actions workflow for HACS repository validation.

## [1.0.1] - 2026-10-17

- Add a selectable YouTube Content Search provider and YouTube search/play tool for compatible Assist conversation agents.
- Restrict playback targets to registered Google Cast media players.
- Persist Home Assistant local playlists and restore them after restarts.
- Improve YouTube API error reporting while keeping API keys and raw response details out of user-facing errors.
- Keep the integration service-only; the sidebar panel and HTTP search endpoints are inactive.
