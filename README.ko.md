# Assist Google TV

[English](README.md) | [한국어](README.ko.md)

[변경 기록](CHANGELOG.md)

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)
![version](https://img.shields.io/badge/version-v1.1.0-blue.svg?style=for-the-badge)
[![kofi](https://img.shields.io/badge/Ko--fi-Support%20Me-F16061?style=for-the-badge&logo=ko-fi)](https://ko-fi.com/plplaaa2)

Assist 음성 명령을 중심으로 Home Assistant 액션에서 YouTube 영상을 검색·재생하거나 Netflix 작품·회차를 Android TV 앱 링크로 엽니다.
현재 사이드바 패널과 HTTP 검색 경로는 등록하지 않습니다.

## 설치와 설정

### 자동설치(권장)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=plplaaa2&repository=https%3A%2F%2Fgithub.com%2Fplplaaa2%2Fassist_google_tv&category=integration)

위 뱃지 클릭 후 설치

### 수동설치

`custom_components/youtube_content_search` 폴더만 HA의 `/config/custom_components/youtube_content_search`로 복사합니다. 호환성을 위해 폴더와 통합 도메인 ID는 기존 값을 유지합니다.


### 설정 방법

1. Google Cloud에서 YouTube Data API v3를 활성화하고 API 키를 준비합니다.
2. Google Cast 또는 Android TV Remote 통합을 설정합니다. 앱 링크 방식은 Google TV의 `remote` 엔티티가 필요합니다.
3. HA를 재시작하고 설정 → 기기 및 서비스 → 통합 추가에서 Assist Google TV를 선택합니다.
4. 설정 화면에 API 키와 재생 방식을 입력합니다. 옵션 변경은 이후 액션 호출부터 적용됩니다.

키는 HA 설정 엔트리에 저장되며, 이 통합은 별도 암호화 저장을 제공하지 않습니다.
자동화 YAML에 실제 키를 넣을 필요는 없습니다.

## 검색 후 재생

개발자 도구 → 액션 또는 자동화/스크립트에서 호출합니다.
영상 검색의 첫 결과를 재생합니다. 재생목록 검색은 지원하지 않습니다. 설정에서 **공식 YouTube 앱 → Cast fallback**, **SmartTube → Cast fallback**, Google Cast만 재생 중 하나를 선택합니다. 기본값은 SmartTube 링크를 먼저 시도한 뒤 실패하면 Cast로 요청합니다.
앱 링크 방식은 Android TV Remote의 `remote` 엔티티와 Google Cast의 `media_player`를 모두 지정해야 합니다. `entity_id`에는 remote, `cast_entity_id`에는 fallback Cast 플레이어를 사용합니다. SmartTube는 YouTube 딥링크로 열며, TV의 앱 선택 화면에서 SmartTube를 기본 앱으로 지정해야 할 수 있습니다.

```yaml
action: youtube_content_search.search_play
data:
  query: "아이유 라이브"
  entity_id: remote.living_room_tv
  cast_entity_id: media_player.living_room_tv
```

검색 없이 특정 영상을 재생하려면 `query` 대신 `video`에 YouTube 영상 URL 또는 11자리 영상 ID를 지정합니다. `query`와 `video`는 둘 중 하나만 입력합니다.

```yaml
action: youtube_content_search.search_play
data:
  video: "https://youtu.be/dQw4w9WgXcQ"
  entity_id: remote.living_room_tv
  cast_entity_id: media_player.living_room_tv
```

## Netflix 작품 열기

`netflix_play` 액션은 작품명을 웹 검색해 Netflix 작품 ID를 찾고 Android TV Remote 앱 링크로 엽니다. 시즌과 회차를 함께 지정하면 해당 회차 링크를 실행합니다.

```yaml
action: youtube_content_search.netflix_play
data:
  query: "장송의 프리렌"
  season: 2
  episode: 8
  entity_id: remote.living_room_tv
```

시즌·회차를 생략하면 영화는 바로 재생하고 시리즈는 작품 페이지를 엽니다. Netflix 작품 메타데이터로 영화와 시리즈를 구분하며, 메타데이터 조회가 실패하면 안전하게 작품 페이지를 엽니다. Assist Web Search의 요청·차단 감지·브라우저 지문 재시도·결과 파싱 방식을 Netflix 검색 코드에 자체 이식했으며, Assist Web Search 설치 없이 단독으로 동작합니다. 검색 차단이나 결과 HTML 구조 변경은 조회 오류로 표시합니다. 검색 결과가 여러 개일 때 첫 번째 Netflix 링크를 사용합니다. 회차 ID 추출은 Netflix 페이지에 포함된 ID를 정렬해 연속 구간별 시즌으로 간주합니다.

## Assist 도구 연결

업데이트한 통합 폴더를 설치하고 HA를 재시작합니다. 도구 호출을 지원하는 LLM 대화 에이전트가 필요합니다.

1. 설정 → 음성 어시스턴트에서 Android TV Remote와 Cast 플레이어를 모두 Assist에 노출합니다.
2. 대화 에이전트 설정의 **Tool providers** 또는 **Control Home Assistant / LLM API**에서 **Assist Google TV (YouTube)**와 **Assist Google TV (Netflix)**를 각각 선택할 수 있습니다. 두 공급자는 별도로 등록됩니다.
3. YouTube만 쓰려면 YouTube 공급자만, Netflix만 쓰려면 Netflix 공급자만 선택하세요. 기본 **Assist** API에는 도구를 자동 추가하지 않습니다.
4. 해당 대화 에이전트를 사용하는 음성 어시스턴트에 “거실 TV에서 유튜브 아이유 라이브 틀어줘”처럼 요청합니다.

도구 이름은 `youtube_content_search__search_play`이며 입력은 검색어 `query` 또는 영상 URL/ID `video`와 `entity_id`입니다. `query`와 `video`는 하나만 지정합니다.
앱 링크 방식은 Android TV Remote와 Google Cast 대상 두 개를 전달합니다. 두 엔티티의 통합 소속을 실행 직전에 확인합니다.
대상이 모호하면 에이전트가 되묻도록 안내합니다. 대상 TV는 설정한 재생 방식의 통합으로 연결되어 있어야 합니다.
Netflix 도구 이름은 `youtube_content_search__netflix_play`이며 `query`, Android TV Remote `entity_id`와 선택적인 `season`·`episode`를 받습니다. YouTube 도구와 별도로 선택할 수 있고, YouTube API 키를 사용하지 않습니다.
성공 응답은 재생 요청을 전달했다는 뜻이며, 실제 화면이나 소리의 재생 성공을 확인한 것은 아닙니다.
재생목록 저장·삭제는 Assist 도구로 제공하지 않습니다. API 키와 백엔드 오류 원문은 LLM에 전달하지 않습니다.

HA 버전과 대화 에이전트에 따라 설정 명칭이 다를 수 있습니다. 기본 내장 대화 에이전트는 이 LLM 도구를 호출하지 않습니다.
Windows 모의 테스트로 공급자 등록·해제·재로드, API 도구 탐색, 권한 변경 및 오류 처리를 검증했으며 실제 HA에서의 목록 표시와 음성 재생은 별도 확인이 필요합니다.

목록에 없다면 통합 파일이 설치되었는지, HA 재시작 후 통합이 정상 로드되었는지 확인하고 대화 에이전트 설정 창을 다시 여세요. 이 통합은 선택한 재생 방식에 따라 Cast 또는 Android TV Remote 대상을 Assist에 제공합니다.

공식 인터페이스: [HA LLM API 및 도구 기여](https://developers.home-assistant.io/docs/core/llm/).

## HA 내부 재생목록

YouTube 계정은 변경하지 않습니다. 영상 정보를 조회해 HA 내부 저장소에 저장합니다.
목록은 HA 재시작 및 통합 재로드 후 자동 복원됩니다. 목록 전체 재생 액션은 제공하지 않습니다.
목록 이름의 하이픈 등은 밑줄로 정규화되며 중복 영상은 합칩니다.

저장 위치는 HA 설정 폴더의 `.storage/youtube_content_search.playlists`입니다.
목록 추가·삭제는 저장을 마친 뒤 HA 상태에 반영하며, 삭제한 목록은 재시작 후에도 삭제 상태를 유지합니다.
백업할 때 이 저장 파일도 포함하세요. 저장 파일을 직접 수정할 필요는 없습니다.
통합 엔트리를 제거해도 저장 파일은 보존되며, 다시 설정하면 목록을 복원합니다.
기존 임시 목록이 HA 상태에 남아 있고 저장 파일이 없다면 처음 초기화할 때 함께 저장합니다.
업데이트를 적용하기 전에 HA를 재시작해 이미 사라진 임시 목록은 복구할 수 없습니다.
관리 UI는 다음 단계에서 결정하며, 현재는 기존 액션과 개발자 도구 → 상태를 사용합니다.

```yaml
action: youtube_content_search.playlist_save
data:
  playlist_id: "my_music"
  video_ids:
    - "dQw4w9WgXcQ"
    - "jNQXAC9IVRw"
```

`video_ids`는 YAML 목록, 쉼표 구분 문자열, JSON 배열 문자열을 받습니다.
개발자 도구 → 상태에서 `youtube_content_search._playlist_my_music`의 `data` 속성을 확인합니다.

```yaml
action: youtube_content_search.playlist_delete
data:
  id: "my_music"
```

## 문제 해결과 제거

API 오류나 검색 결과 없음은 액션 오류로 표시됩니다. API 사용량과 권한은 Google Cloud에서 확인합니다.
API 오류에는 HTTP 상태와 허용된 사유 코드만 표시합니다. 키·요청 URL·응답 원문은 표시하지 않습니다.
예를 들어 `HTTP 400 (reason: invalidFilters)`는 요청 필터를, `API_KEY_INVALID`는 키 유효성을 확인해야 합니다.
`SERVICE_DISABLED`는 API 활성화 상태, `quotaExceeded`는 API 사용량 한도를 확인합니다.
알 수 없는 코드나 JSON이 아닌 응답은 `reason: UNKNOWN`으로 표시합니다.
파일 업데이트 후 HA를 재시작합니다. 통합 엔트리 제거 시 런타임 자격 정보가 제거됩니다.
코드 제거는 HACS 또는 수동 설치 폴더 삭제 후 재시작으로 진행합니다.
프런트엔드 파일과 미연결 `options_flow.py`는 보존했습니다. 활성 옵션 흐름은 `config_flow.py`에 있습니다.

## 개발 검증

Windows Python 환경에서 aiohttp와 voluptuous를 설치한 뒤 실행합니다.

```powershell
python -B -m unittest discover -s tests -v
```

테스트는 HA 인터페이스를 모의 구현하고 임시 파일로 재생목록 복원을 검증합니다.
실제 HA Store 동작·설정 로딩·API 인증·TV 앱 링크 재생은 별도 확인이 필요합니다.
외부 통합 버전은 `1.1.0`입니다.
HACS 검증 GitHub Action은 push, pull request, 매일 정기 실행, 수동 실행 시 저장소를 통합 카테고리로 검증합니다.

## 공식 참고 자료

- [HA manifest](https://developers.home-assistant.io/docs/creating_integration_manifest/)
- [HA 사용자 정의 통합 번역](https://developers.home-assistant.io/docs/internationalization/custom_integration/)
- [Google Cast YouTube 재생](https://www.home-assistant.io/integrations/cast/#youtube)
- [YouTube 영상 메타데이터](https://developers.google.com/youtube/v3/docs/videos/list)
- [HACS 배포 요건](https://www.hacs.xyz/docs/publish/integration/)
