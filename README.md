# YouTube Content Search

Home Assistant 서비스(액션)로 YouTube 영상을 검색해 Google Cast 기기에서 재생합니다.
현재 사이드바 패널과 HTTP 검색 경로는 등록하지 않습니다.

## 설치와 설정

1. Google Cloud에서 YouTube Data API v3를 활성화하고 API 키를 준비합니다.
2. HA의 Google Cast 통합을 설정하고 `media_player` 엔티티를 확인합니다.
3. 수동 설치는 `custom_components/youtube_content_search` 폴더만 HA의 `/config/custom_components/youtube_content_search`로 복사합니다.
4. HA를 재시작하고 설정 → 기기 및 서비스 → 통합 추가에서 YouTube Content Search를 선택합니다.
5. 설정 화면에 API 키를 입력합니다. 옵션 변경은 이후 액션 호출부터 적용됩니다.

키는 HA 설정 엔트리에 저장되며, 이 통합은 별도 암호화 저장을 제공하지 않습니다.
자동화 YAML에 실제 키를 넣을 필요는 없습니다.

## 검색 후 재생

개발자 도구 → 액션 또는 자동화/스크립트에서 호출합니다.
영상 검색의 첫 결과를 재생합니다. 재생목록 검색은 지원하지 않습니다.
대상은 YouTube 앱을 지원하는 Google Cast 기기여야 합니다.

```yaml
action: youtube_content_search.search_play
data:
  query: "아이유 라이브"
  entity_id: media_player.living_room_tv
```

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
파일 업데이트 후 HA를 재시작합니다. 통합 엔트리 제거 시 런타임 자격 정보가 제거됩니다.
코드 제거는 HACS 또는 수동 설치 폴더 삭제 후 재시작으로 진행합니다.
프런트엔드 파일과 미연결 `options_flow.py`는 보존했습니다. 활성 옵션 흐름은 `config_flow.py`에 있습니다.

## 개발 검증

Windows Python 환경에서 aiohttp와 voluptuous를 설치한 뒤 실행합니다.

```powershell
python -B -m unittest discover -s tests -v
```

테스트는 HA 인터페이스를 모의 구현하고 임시 파일로 재생목록 복원을 검증합니다.
실제 HA Store 동작·설정 로딩·API 인증·Cast 재생은 별도 확인이 필요합니다.
외부 버전은 기존 `1.0.0`을 유지합니다.

## 공식 참고 자료

- [HA manifest](https://developers.home-assistant.io/docs/creating_integration_manifest/)
- [HA 사용자 정의 통합 번역](https://developers.home-assistant.io/docs/internationalization/custom_integration/)
- [Google Cast YouTube 재생](https://www.home-assistant.io/integrations/cast/#youtube)
- [YouTube 영상 메타데이터](https://developers.google.com/youtube/v3/docs/videos/list)
- [HACS 배포 요건](https://www.hacs.xyz/docs/publish/integration/)
