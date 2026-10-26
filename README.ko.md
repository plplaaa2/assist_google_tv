# Assist Google TV

Home Assistant Assist 음성 명령으로 Google TV에서 YouTube 영상을 검색·재생하고 Netflix 작품과 회차를 엽니다. YouTube 재생목록도 Home Assistant 내부에 저장할 수 있습니다.

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)
![버전](https://img.shields.io/badge/version-v1.0.0-blue.svg?style=for-the-badge)
[![Ko-fi](https://img.shields.io/badge/Ko--fi-Support%20Me-F16061?style=for-the-badge&logo=ko-fi)](https://ko-fi.com/plplaaa2)

[English](README.md)

## 설치

### HACS

[![Home Assistant에서 저장소 열기](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=plplaaa2&repository=https%3A%2F%2Fgithub.com%2Fplplaaa2%2Fassist_google_tv&category=integration)

통합을 설치하고 Home Assistant를 재시작한 다음 **설정 → 기기 및 서비스 → 통합 추가**에서 **Assist Google TV**를 추가합니다.

### 수동 설치

`custom_components/assist_google_tv` 폴더를 HA의 `/config/custom_components/assist_google_tv`에 복사하고, HA를 재시작한 뒤 **Assist Google TV**를 추가합니다.

## 설정

Home Assistant에서 Google Cast 및/또는 Android TV Remote를 먼저 설정한 다음 통합 추가 화면을 진행합니다.

1. YouTube Data API v3 키를 입력합니다. 입력값은 비밀번호 형식으로 가려집니다.
2. 앱을 실행할 Google TV 제어 방식(Android TV Remote 또는 ADB)과 TV 엔티티를 선택합니다.
3. 감지된 앱 체크박스에서 사용할 앱을 고릅니다. 감지가 비어 있거나 앱이 빠졌다면 `[{"name":"YouTube","launch":"https://www.youtube.com"}]` 형태의 JSON 배열로 추가할 수 있습니다. Remote는 옵션에 등록된 앱을, ADB는 TV에서 조회한 앱과 `source_list` 후보를 보여줍니다.
4. YouTube 재생 방식을 선택합니다.

- **SmartTube → Cast fallback** (기본값)
- **공식 YouTube 앱 → Cast fallback**
- **Google Cast만 사용**

앱 링크 방식은 Android TV Remote의 `remote` 엔티티와 fallback용 Google Cast `media_player`가 필요합니다. Cast 전용 방식은 Google Cast `media_player`를 사용합니다. Netflix 액션은 Android TV Remote를 사용하며 YouTube API 키가 필요하지 않습니다. 설정 마지막 단계에서 Netflix 검색 지역을 선택할 수 있으며, 선택한 지역의 Netflix 작품 페이지로 검색 범위를 제한합니다. 기본 지역은 대한민국입니다.

옵션에서 키를 바꿀 때 입력란을 비워 두면 기존 키를 유지합니다. API 키는 자동화 YAML에 넣지 마세요.

## 액션

### YouTube 검색 및 재생

검색어 `query` 또는 YouTube 영상 URL/ID `video` 중 하나를 입력합니다.

```yaml
action: assist_google_tv.youtube_search_play
data:
  query: "아이유 라이브"
  entity_id: remote.living_room_tv
  cast_entity_id: media_player.living_room_tv
```

특정 영상을 바로 재생하려면 다음처럼 입력합니다.

```yaml
action: assist_google_tv.youtube_search_play
data:
  video: "https://youtu.be/dQw4w9WgXcQ"
  entity_id: remote.living_room_tv
  cast_entity_id: media_player.living_room_tv
```

Cast 전용 모드에서는 `entity_id`에 `media_player`를 지정합니다. `cast_entity_id`는 앱 링크 fallback 방식에서만 필요합니다.

### Netflix 작품 열기

화면 보호기가 전면에 있으면 YouTube/Netflix 재생 또는 설정 앱 실행 전에 자동으로 닫습니다. Netflix 작품명과 Android TV Remote 엔티티를 지정합니다. 특정 시즌의 회차는 `season`과 `episode`를 함께 입력하고, 시즌 없이 회차만 지정하면 Netflix의 전체 누적 회차 번호로 찾습니다. 회차를 지정하지 않으면 영화는 바로 재생하고 시리즈는 작품 페이지를 엽니다.

```yaml
action: assist_google_tv.netflix_play
data:
  query: "장송의 프리렌"
  season: 2
  episode: 8
  entity_id: remote.living_room_tv
```

### 재생목록 저장과 삭제

재생목록은 Home Assistant 내부에 저장되며 YouTube 계정은 변경하지 않습니다.

```yaml
action: assist_google_tv.youtube_playlist_save
data:
  playlist_id: "my_music"
  video_ids:
    - "dQw4w9WgXcQ"
    - "jNQXAC9IVRw"
```

`video_ids`는 쉼표로 구분한 문자열이나 JSON 배열 문자열도 받을 수 있습니다.

```yaml
action: assist_google_tv.youtube_playlist_delete
data:
  id: "my_music"
```

저장된 재생목록 요약을 조회하고, `playlist_id`를 지정해 영상 제목·채널·순번을 확인할 수 있습니다. 자동화에서는 응답을 변수로 받습니다.

```yaml
action: assist_google_tv.youtube_playlist_list
data:
  playlist_id: "my_music"
response_variable: playlist
```

재생목록 전체를 저장된 순서대로 재생하려면 다음 액션을 사용합니다. 앱 링크 방식에서는 첫 영상은 Android TV Remote로 열고, 이후 영상은 같은 TV의 Cast 엔티티 대기열에 추가합니다. Cast 전용 방식에서는 `entity_id`에 Cast 플레이어를 지정합니다.

```yaml
action: assist_google_tv.youtube_playlist_play
data:
  playlist_id: "my_music"
  entity_id: remote.living_room_tv
  cast_entity_id: media_player.living_room_tv
```

## Assist 음성 명령

1. 사용할 Android TV Remote 및/또는 Google Cast 엔티티를 Assist에 노출합니다.
2. 통합 옵션의 순서형 설정을 진행해 Remote 또는 ADB 방식과 TV 엔티티를 고른 다음 앱 체크박스를 확인합니다. 감지되지 않은 앱만 `{"name":"YouTube","launch":"https://www.youtube.com"}` 형식의 JSON으로 추가하세요. Remote의 `launch`는 activity/deep link, ADB의 `launch`는 앱 패키지 ID를 사용합니다.
3. 도구 호출을 지원하는 대화 에이전트 설정에서 **Assist Google TV (YouTube)**, **Assist Google TV (Netflix)**, **Assist Google TV (App Launch)** 중 필요한 공급자를 선택합니다. 각각 독립적으로 선택할 수 있습니다.
4. 음성 어시스턴트에 YouTube 영상 재생, Netflix 작품 열기, 설정된 앱 실행, 또는 Google TV 홈 화면 이동을 요청합니다.

YouTube 도구 이름은 `assist_google_tv__youtube_search_play`입니다. Netflix 도구 이름은 `assist_google_tv__netflix_play`이며 YouTube API 키 없이 사용할 수 있습니다. 앱 실행 provider는 `assist_google_tv__open_app`과 `assist_google_tv__go_home`을 제공하고, ADB 방식에서는 `assist_google_tv__stop_app`도 제공합니다. 홈 이동은 Remote의 `HOME` 키 또는 ADB의 `HOME` 명령을 보냅니다. 재생목록 액션은 Home Assistant 액션으로 제공하며 Assist 도구에는 포함하지 않습니다.

성공 응답은 Home Assistant가 재생 요청을 보냈다는 뜻이며, 실제 영상이나 소리의 재생을 확인한 것은 아닙니다.

## 개발 확인

```powershell
python -B -m unittest discover -s tests -v
python -B validate_syntax.py
```

## 기여 및 라이선스

[plplaaa2](https://github.com/plplaaa2)가 관리하며, [OpenAI Codex](https://openai.com/codex/)의 도움을 받아 개발했습니다.

Netflix 작품 검색의 DuckDuckGo HTML 요청 형식, 결과 파싱 방식, 브라우저 지문 fallback은 [Nick Clyde의 `duckduckgo-mcp-server`](https://github.com/nickclyde/duckduckgo-mcp-server)를 바탕으로 하거나 그 구현에서 영감을 받았습니다. 원본은 MIT 라이선스이며 MCP 실행 코드는 포함하지 않습니다. 필요한 저작권 및 허가 고지는 [`THIRD_PARTY_NOTICES.md`](custom_components/assist_google_tv/THIRD_PARTY_NOTICES.md)에 보존했습니다. 그 외 프로젝트 코드는 저장소의 [MIT 라이선스](LICENSE)를 따릅니다.

\n
