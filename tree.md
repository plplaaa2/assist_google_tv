# Project structure

HA service integration with Assist LLM tools. Frontend assets are retained but inactive.

```text
LICENSE
README.md
README.ko.md
CHANGELOG.md
changelog.jsonl
.github/workflows/validate.yaml
custom_components/assist_google_tv/__init__.py
custom_components/assist_google_tv/config_flow.py
custom_components/assist_google_tv/brand/icon.png
custom_components/assist_google_tv/const.py
custom_components/assist_google_tv/llm.py
custom_components/assist_google_tv/frontend/panel.html
custom_components/assist_google_tv/frontend/panel.js
custom_components/assist_google_tv/frontend/styles.css
custom_components/assist_google_tv/manifest.json
custom_components/assist_google_tv/options_flow.py
custom_components/assist_google_tv/playlist_store.py
custom_components/assist_google_tv/services.py
custom_components/assist_google_tv/services.yaml
custom_components/assist_google_tv/translations/en.json
custom_components/assist_google_tv/translations/ko.json
hacs.json
icon.png
info.md
logo.png
tests/test_service_only.py
tree.md
validate_syntax.py
```

servers/ contains only Git metadata and is outside the integration runtime.
