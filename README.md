# CGV Open Push Email

개인용 CGV 예매 오픈 알림 서비스입니다. 상영 일정 조회 결과에서 새로 추가된 회차만 SQLite에 기록하고 이메일로 알립니다.

현재 CGV의 최신 요청 형식은 공개된 `cgv-open-push`의 구형 API와 다르므로, 조회 URL과 요청 JSON은 환경 변수로 주입합니다. 구형 코드의 고정 쿠키와 `verify=False` 설정은 사용하지 않습니다.

## 실행

```bash
cp .env.example .env
# .env에 CGV 요청값과 SMTP 정보를 입력
docker compose up --build
```

메일 인증 정보는 저장소에 커밋하지 않습니다. `.env`는 로컬 파일로만 관리합니다.

## 필요한 설정

`CGV_REQUEST_JSON`은 CGV 일정 조회 요청의 JSON 객체입니다. `CGV_HEADERS_JSON`과 `CGV_COOKIES_JSON`은 필요한 경우에만 지정합니다.

처음 실행할 때는 현재 일정을 기준 상태로만 저장하고 메일을 보내지 않습니다. 이후 새 회차가 추가되면 메일을 발송합니다.

## 라이선스

원본 코드를 포함하는 경우 GNU AGPL-3.0 조건을 따릅니다. 이 저장소의 구현은 개인용으로 작성되며, 원본 저작권과 라이선스 고지를 유지합니다.
