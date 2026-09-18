# KaiXin NAVER v3

Django 기반 프로젝트입니다. 방문자용 네이버 스타일 로그인 페이지(`accounts`), 관리자 콘솔(`kaixin`), 네이버 메일 이미지 뷰어(`mybox`)가 분리되어 있습니다.

## 요구 사항

- Python 3.10+
- Django 6.x (`requirements.txt` 참고)

## 설치

`db.sqlite3`는 저장소에 포함되지 않습니다. **clone 후 반드시 `migrate`를 실행**해야 테이블이 생성됩니다.  
(`OperationalError: no such table: accounts_blacklistpolicy` 는 migrate 미실행이 원인입니다.)

pull 후에도 새 마이그레이션이 있으면 다시 `migrate` 합니다.

```bash
git clone <repo-url> KaiXin_NAVER_v3
cd KaiXin_NAVER_v3

python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

pip install -r requirements.txt
python manage.py migrate
```

데이터는 Django 표준 **SQLite**(`db.sqlite3`)에 저장됩니다. migrate를 다시 실행해도 기존 데이터는 유지됩니다.

nginx/Cloudflare 뒤에서 돌릴 때는 방문자 IP가 `127.0.0.1`로 보이지 않도록 헤더를 넘깁니다. 도메인으로 띄우면 관리자 MYBOX 탭의 Image URL도 그 호스트를 따릅니다.

```nginx
proxy_set_header Host $host;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-Proto $scheme;
```

## 실행

```bash
source venv/bin/activate   # 새 셸이면 활성화 필요
python manage.py runserver
# 외부 접속 허용
python manage.py runserver 0.0.0.0:8000
```

기본 주소: `http://127.0.0.1:8000/`

`127.0.0.1` / `::1` 로 연 로컬 접속은 블랙리스트·횟수 집계 대상이 아닙니다. LAN IP나 도메인으로 시험해야 자동 차단이 동작합니다.

## 엔드포인트

### 방문자 (`accounts`)

| 경로 | 설명 |
|------|------|
| `/` 및 그 외 미등록 경로 | 네이버 스타일 로그인 페이지 |
| `/login-intro-mybox/` | 로그인 인트로용 MYBOX iframe (방문 횟수에 포함하지 않음) |
| `/robots.txt` | `Disallow: /` 및 함정 경로 |

- GET/POST 요청은 SQLite `accounts_requestlog` 테이블에 기록됩니다.
- URL 쿼리 `?id=아이디`로 아이디 입력칸을 미리 채울 수 있습니다. 파라미터가 없으면 빈 상태입니다.
- URL 쿼리 `url` / `redirect` / `redirect_url`에 안전한 `http`/`https` 절대 URL이 있으면, Loading 인트로에서 로그인 시도 한도에 도달해 `login` kind로 등록될 때와, 이미 `login`으로 차단된 뒤 다시 방문할 때 그 URL로 리다이렉트합니다(없으면 Login Redirect URL). MYBOX 인트로에서는 이 파라미터를 무시하고 `/mybox/`를 엽니다. POST 시에도 쿼리·hidden 필드로 값이 유지됩니다.
- OS/브라우저 다크 모드(`prefers-color-scheme: dark`)에 맞춰 라이트/다크 테마가 자동 적용됩니다.
- 로그인 인트로는 관리자 Login 탭에서 둘 중 하나를 고릅니다.
  - **Loading:** 로딩 페이지 → 네트워크 오류 → 로그인. 한도 도달 시 요청의 리다이렉트 URL(위) 또는 Login Redirect URL
  - **MYBOX:** MYBOX 뷰어 → 네트워크 오류 → 로그인. ID+비밀번호 POST가 한도에 미달이면 비밀번호 오류, 한도에 도달하면 뷰어로 이동한 뒤 해당 IP를 차단합니다.

**예시**

```
http://127.0.0.1:8000/?id=myuser
http://127.0.0.1:8000/?id=myuser&locale=en
http://127.0.0.1:8000/?id=myuser&url=https://return.example/
```

### 파일 다운로드

관리자 **Files**에서 업로드한 파일은 중간 경로와 관계없이 **파일명만** 맞으면 받을 수 있습니다.

| 경로 | 설명 |
|------|------|
| `/download/<임의경로>/<filename>` | GET 시 등록된 파일이면 attachment로 전송. 중간 경로는 임의(매칭에 사용하지 않음) |
| `/download/...` (없는 파일·불완전 경로) | 404 대신 **Download Redirect URL**로 리다이렉트 (블랙리스트 Redirect와 동일 방식) |

- 중간 경로(`docs-2026`, `a/b/c` 등)는 자유롭게 쓸 수 있으며 DB에 저장·검증하지 않습니다.
- 같은 다운로드 이름은 하나만 올릴 수 있습니다. 파일은 `media/downloads/<id>/` 아래에 저장됩니다 (`DOWNLOAD_MAX_BYTES`, 기본 50MB).
- 없는 파일명, 디스크에 파일이 없는 경우, `/download/한세그먼트만`처럼 형식이 맞지 않는 경로도 모두 Download Redirect URL로 보냅니다.
- Redirect URL은 `/kaixin-judy-yuna/files/` 의 **Missing download redirect**에서 저장·Reset합니다. 기본값은 `DOWNLOAD_REDIRECT_URL`(`settings.py`)입니다.
- `/download/` 는 블랙리스트·rate/bot 차단에서 제외됩니다.

**예시** (`report.pdf`를 올려 둔 경우 아래가 모두 동일 파일을 받음)

```
http://127.0.0.1:8000/download/x/report.pdf
http://127.0.0.1:8000/download/anything/report.pdf
http://127.0.0.1:8000/download/a/b/c/report.pdf
```

**없는 경로 → 리다이렉트 예시**

```
http://127.0.0.1:8000/download/adkjapdojciopqhjdpociqjcopiqijw/djfjoqjpoijpsaoidjcojadpajksdl
→ Download Redirect URL (기본 https://www.naver.com/)
```

### 이미지 뷰어 (`mybox`)

네이버 메일 첨부 이미지 뷰어를 검은 배경으로 재현한 페이지입니다. 메일 본문은 표시하지 않습니다.

| 경로 | 설명 |
|------|------|
| `/mybox/` 및 `/mybox/...` | 이미지 뷰어 (`/mybox/` 아래 임의 경로 포함) |

- PC(1024px 이상): 파일명·다운로드·MYBOX 저장·닫기가 상단, `1/1`이 하단, 좌우 화살표 표시
- 모바일: 닫기·파일명·용량·페이지 번호가 상단, 다운로드·MYBOX 저장이 하단
- User-Agent와 화면 너비로 `pc` / `aos` / `ios` 클래스를 적용합니다
- **다운로드**는 표시 중인 이미지를 저장하고, **MYBOX 저장**은 안내 토스트만 표시합니다
- `/mybox/` 방문은 IP별 횟수가 DB에 쌓입니다. rate/login/total 차단은 `/mybox/`에 적용되지 않고, MYBOX 방문 한도와 Bot 차단만 적용됩니다
- `/static/mybox/`, `/media/mybox/` 는 방문 횟수에 넣지 않습니다
- 업로드한 뷰어 이미지는 `/media/mybox/viewer` + 확장자로 제공됩니다 (`config/settings.py` → `MEDIA_URL` / `MEDIA_ROOT`)

**예시**

```
http://127.0.0.1:8000/mybox/
http://127.0.0.1:8000/mybox/anything
```

### 관리자 (`kaixin`)

| 경로 | 설명 |
|------|------|
| `/20020522/judy/` | Sign In |
| `/20100514/yuna/` | Sign Up |
| `/kaixin-judy-yuna/` | 대시보드 (IP별 요청 기록) |
| `/kaixin-judy-yuna/export/` | 요청 로그 JSON export (전체 또는 IP·기간 필터) |
| `/kaixin-judy-yuna/logs/<ip>/` | 해당 IP 요청 상세 |
| `/kaixin-judy-yuna/admins/` | 관리자 승인 (최고관리자만) |
| `/kaixin-judy-yuna/files/` | 다운로드 파일 업로드·목록·삭제, Missing download redirect URL |
| `/kaixin-judy-yuna/blacklist/` | Blocked IPs (추가·삭제·전체 삭제) |
| `/kaixin-judy-yuna/blacklist/limits/` | Request Limits |
| `/kaixin-judy-yuna/blacklist/login/` | Login 한도·인트로 |
| `/kaixin-judy-yuna/blacklist/mybox/` | MYBOX 방문 한도·뷰어 이미지/이름/용량·방문 기록 |
| `/kaixin-judy-yuna/blacklist/bots/` | Bot 자동 차단 (UA·경로 키워드 포함) |
| `/kaixin-judy-yuna/blacklist/unknown/` | Unknown device/OS 자동 차단 |
| `/kaixin-judy-yuna/logout/` | Sign Out |

관리자 UI 문구는 영문입니다. 콘솔(`/kaixin-judy-yuna/`)은 Bootstrap 5.3과 다크 테마를 함께 씁니다. Sign In / Sign Up 게이트는 기존 `auth.css`입니다. 대시보드·블랙리스트 IP 목록은 페이지당 25개씩 pagination 됩니다. 상단 내비 **Files**에서 공개 다운로드 파일과 없는 `/download/...` 경로용 Redirect URL을 관리합니다.

## 관리자 권한

1. **첫 가입자** → 최고관리자(superadmin), 즉시 승인
2. **이후 가입자** → 승인 대기. Sign In 시 안내 메시지 표시
3. 최고관리자가 `/kaixin-judy-yuna/admins/` 에서 승인·철회·삭제

Django `createsuperuser` / `django.contrib.auth` User 모델은 사용하지 않습니다. 관리자 계정은 `kaixin_adminuser` 테이블에 저장됩니다.

## 데이터베이스 (SQLite)

| 테이블 | 용도 |
|--------|------|
| `accounts_requestlog` | 방문자 요청 로그 |
| `accounts_blacklistentry` | IP 블랙리스트 (`kind`별) |
| `accounts_blacklistpolicy` | 자동 차단 정책 + Download Redirect URL 등 (단일 행) |
| `accounts_loginattemptcounter` | IP별 로그인 POST 횟수 |
| `accounts_myboxvisitcounter` | IP별 `/mybox/` 방문 횟수 |
| `accounts_downloadfile` | 공개 다운로드 파일 (파일명 기준, `media/downloads/`) |
| `kaixin_adminuser` | 관리자 계정 |

DB 파일 경로: 프로젝트 루트 `db.sqlite3` (`config/settings.py` → `DATABASES`)

요청 로그·관리자 화면의 시각은 KST(`Asia/Seoul`)입니다. DB에는 UTC로 저장됩니다.

로그인 시도·MYBOX 방문 횟수는 gunicorn 워커가 여러 개여도 SQLite에 공유됩니다.

## IP 차단

차단 IP는 `/kaixin-judy-yuna/blacklist/` 에서 추가·삭제합니다. 상단 탭으로 설정을 나눕니다. 각 kind의 차단 목록은 `accounts_blacklistentry`만 사용합니다(별도 hit 이력 테이블 없음).

| 탭 | 경로 | 내용 |
|----|------|------|
| Blocked IPs | `/kaixin-judy-yuna/blacklist/` | IP 추가, 전체 kind 목록, 개별/전체 삭제. 수동 차단 Redirect URL |
| Request Limits | `/blacklist/limits/` | rate limit, 총 요청 한도, Limits Redirect URL, rate/limit 차단 IP 목록 |
| Login | `/blacklist/login/` | 로그인 시도 한도, 인트로 시퀀스, Login Redirect URL(요청 `url` 등 파라미터가 없을 때), login 차단 IP 목록 |
| MYBOX | `/blacklist/mybox/` | 방문 한도, MYBOX Redirect URL, 뷰어 이미지·이름·용량·제목, 방문 횟수 기록 |
| Bots | `/blacklist/bots/` | UA·스캐너 경로·Path keywords·honeypot·webdriver, Bot Redirect URL, bot 차단 IP 목록 |
| Unknown | `/blacklist/unknown/` | device/OS Unknown 자동 차단, Unknown Redirect URL, unknown 차단 IP 목록 |

각 탭의 Save / Reset은 그 탭 설정만 바꿉니다. kind마다 Redirect URL이 따로 있습니다.

| kind | 설명 | Redirect |
|------|------|----------|
| `manual` | 수동 차단 | Blocked IPs |
| `login` | 로그인 시도 한도 초과 | Login |
| `bot` | 봇 탐지 | Bots |
| `unknown` | device 또는 OS가 Unknown | Unknown |
| `rate` | 짧은 시간 과다 요청 | Request Limits |
| `limit` | IP별 누적 요청 한도 초과 | Request Limits |
| `mybox` | `/mybox/` 방문 한도 초과 | MYBOX |

이미 올라간 IP의 우선순위는 **manual → login → bot → unknown → rate → limit** 입니다. `mybox`는 `/mybox/`에만 적용됩니다.

- 관리자 경로(`/20020522/judy`, `/20100514/yuna`, `/kaixin-judy-yuna`)와 `/robots.txt`, `/download/`는 차단 대상에서 제외됩니다.
- 로컬 주소(`127.0.0.1`, `::1`)는 자동·수동 차단과 횟수 집계가 모두 꺼집니다.
- 리스트에서 해당 IP(또는 kind 전체)를 지우면 그 kind 차단이 풀립니다. `login`/`mybox`를 지우면 해당 횟수 카운터도 초기화됩니다.
- MYBOX 탭의 방문 횟수 기록을 지우면 그 IP의 `mybox` 차단도 풀립니다.

### 로그인 시도

ID와 비밀번호가 모두 있는 POST만 셉니다. 빈 필드는 세지 않습니다. 기본 한도는 2입니다.

- 한도 미만: 로그인 화면에 비밀번호 오류
- 한도 도달, Loading 인트로: `login` kind로 등록한 뒤 리다이렉트. 우선순위는 요청의 `url` → `redirect` → `redirect_url`(안전한 http/https 절대 URL만) → Login Redirect URL. `javascript:`·상대 경로·기타 스킴은 무시합니다. 이미 `login`으로 차단된 IP가 같은 파라미터로 재방문해도 동일하게 적용됩니다(우선 kind가 `manual`이면 Login Redirect URL·요청 파라미터를 쓰지 않음).
- 한도 도달, MYBOX 인트로: `/mybox/`를 연 뒤 그 IP를 `login`으로 등록. 요청 리다이렉트 파라미터는 쓰지 않습니다. 이후 로그인 페이지 재방문은 Login Redirect URL(요청에 안전한 `url` 등이 있으면 그쪽)
### MYBOX 방문

`/mybox/` 아래 페이지 GET마다 횟수가 올라갑니다. 자동 차단을 꺼도 기록은 남습니다. MYBOX 탭에서 방문 횟수(IP·횟수·마지막 방문·차단 여부)를 보고 삭제할 수 있습니다.

뷰어 이미지·표시 이름·용량은 MYBOX 탭 **MYBOX viewer**에서 바꿉니다.

- 보관 이름은 항상 `viewer` + 확장자입니다. 기본 이미지는 `static/mybox/images/viewer.jpg`이고, 올리면 `media/mybox/viewer.jpg`(또는 `.png` / `.gif` / `.webp`)로 덮어씁니다. JPG·PNG·GIF·WebP, 8MB 이하입니다.
- 뷰어 제목과 다운로드 이름은 **Image name**(기본 `20260824_071530`) + 실제 확장자입니다. 디스크 파일명과 별개입니다. File size는 표시 문구만 바꿉니다.
- 관리자 화면 **Image URL**은 지금 이미지를 가리키는 전체 주소입니다. 다른 사이트에서 이 주소를 호출하면 됩니다. 호스트는 관리자 페이지를 연 주소와 같고, 도메인으로 콘솔을 열면 도메인이 붙습니다.
- Reset viewer는 기본 이미지·이름·용량으로 되돌립니다. 업로드 파일은 `media/`에 있으며 git에 넣지 않습니다.

### Bot 차단

기본으로 켜져 있습니다. 로그인과 `/mybox/` 모두에 적용됩니다.

- User-Agent에 curl, wget, python-requests, googlebot, HeadlessChrome, Selenium 등이 포함되거나 UA가 비어 있으면 차단
- 스캐너 경로: `/.env`, `/wp-login.php`, `/xmlrpc.php`, `/.git/config`, `/nids-trap/`
- **Path keywords:** 관리자가 등록한 단어가 요청 경로에 포함되면(대소문자 무시 부분 문자열) `bot`으로 자동 추가
- 로그인 폼의 숨은 honeypot 필드가 채워지면 차단
- `navigator.webdriver`이면 `/nids-trap/` 로 beacon
- Bots 탭 Extra UA keywords / Path keywords는 하나씩 추가·삭제하고, Delete All로 전부 지울 수 있습니다. Save와 별개로 바로 저장됩니다.
- 차단된 IP는 Bots 탭 **Bot blocked IPs**에서 개별·선택·전체 삭제합니다.

### Unknown 차단

요청 로그의 device 또는 OS가 `Unknown`이면 IP를 `unknown` kind로 올리고 Unknown Redirect URL로 보냅니다. Unknown 탭에서 켜고 끌 수 있습니다.

## 설정

`config/settings.py`에 기본값이 정의되어 있으며, 관리자 탭에서 바꾼 값은 SQLite `accounts_blacklistpolicy`에 저장됩니다.

| 항목 | settings.py 기본값 | UI |
|------|-------------------|-----|
| `BLACKLIST_REDIRECT_URL` | `https://www.naver.com/` | Blocked IPs |
| `LIMITS_REDIRECT_URL` | `https://www.naver.com/` | Request Limits |
| `RATE_LIMIT_ENABLED` | `True` | Request Limits |
| `RATE_LIMIT_MAX_REQUESTS` | `80` | Request Limits |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | Request Limits |
| `TOTAL_REQUEST_LIMIT_ENABLED` | `True` | Request Limits |
| `TOTAL_REQUEST_LIMIT_MAX` | `500` | Request Limits |
| `LOGIN_ATTEMPT_REDIRECT_URL` | `https://www.naver.com/` | Login |
| `LOGIN_ATTEMPT_MAX` | `2` | Login |
| `LOGIN_INTRO_MODE` | `loading` (`loading` 또는 `mybox`) | Login |
| `LOGIN_LOADING_ENABLED` | `True` | Login |
| `LOGIN_LOADING_DELAY_MS` | `3000` | Login |
| `LOGIN_LOADING_PROGRESS_PERCENT` | `100` | Login |
| `LOGIN_LOADING_HOLD_MS` | `1000` | Login |
| `LOGIN_SPLASH_ENABLED` | `True` | Login |
| `LOGIN_SPLASH_DELAY_MS` | `1000` | Login |
| `LOGIN_MYBOX_DELAY_MS` | `3000` | Login |
| `MYBOX_REDIRECT_URL` | `https://www.naver.com/` | MYBOX |
| `MYBOX_FILENAME` | `20260824_071530` | MYBOX (뷰어 표시 이름. 디스크 파일명은 `viewer`) |
| `MYBOX_FILESIZE` | `2MB` | MYBOX (표시 문구) |
| `MYBOX_VISIT_LIMIT_ENABLED` | `True` | MYBOX |
| `MYBOX_VISIT_MAX` | `3` | MYBOX |
| `BOT_REDIRECT_URL` | `https://www.naver.com/` | Bots |
| `BOT_BLOCK_ENABLED` | `True` | Bots |
| `BOT_BLOCK_EMPTY_UA` | `True` | Bots |
| `BOT_BLOCK_SCANNER_PATHS` | `True` | Bots |
| `BOT_BLOCK_HONEYPOT` | `True` | Bots |
| `BOT_BLOCK_WEBDRIVER` | `True` | Bots |
| `BOT_UA_KEYWORDS` | (비움) | Bots (Extra UA keywords 초기값) |
| `BOT_PATH_KEYWORDS` | (비움) | Bots (Path keywords 초기값) |
| `UNKNOWN_BLOCK_ENABLED` | `True` | Unknown |
| `UNKNOWN_REDIRECT_URL` | `https://www.naver.com/` | Unknown |
| `DOWNLOAD_MAX_BYTES` | `50 * 1024 * 1024` | Files (업로드 한도) |
| `DOWNLOAD_REDIRECT_URL` | `https://www.naver.com/` | Files (없는 다운로드 경로) |

`LOGIN_LOADING_DELAY_MS`는 로딩 스피너 표시 시간(밀리초)입니다. `0`이면 해당 단계를 건너뜁니다.

`LOGIN_LOADING_PROGRESS_PERCENT`는 로딩 페이지 상단 진행 바가 채워지는 최대 비율(1–100)입니다.

`LOGIN_LOADING_HOLD_MS`는 진행 바가 마지막 %에 도달한 뒤 에러 페이지로 넘어가기 전 정지 시간입니다.

`LOGIN_SPLASH_DELAY_MS`는 네트워크 오류 페이지 표시 시간입니다.

`LOGIN_MYBOX_DELAY_MS`는 MYBOX 인트로가 화면에 머무는 시간입니다.

`MYBOX_FILENAME`은 뷰어에 보이는 이름입니다. 기본·업로드 이미지의 보관 이름은 `viewer` + 확장자입니다.

## 프로젝트 구조

```
├── accounts/              # 방문자 로그인 · IP 미들웨어 · SQLite 모델
│   ├── models.py          # RequestLog, BlacklistEntry, BlacklistPolicy, counters
│   ├── middleware.py      # 블랙리스트 · rate/login/mybox/bot/unknown
│   ├── bot_detect.py      # UA · 스캐너 경로 · Path keywords · honeypot
│   ├── blacklist_store.py # IP 목록 · 횟수 · redirect
│   └── download_store.py  # /download/<any>/<file> 업로드·조회
├── kaixin/                # 관리자 인증 · 대시보드 · 승인 · Files
│   └── models.py          # AdminUser
├── mybox/                 # 네이버 메일 이미지 뷰어
│   └── views.py           # 뷰어 · 인트로 임베드
├── templates/             # 프로젝트 공통 템플릿
│   ├── accounts/          # login.html, 인트로 스플래시
│   ├── kaixin/            # 관리자 콘솔 · blacklist · files
│   └── mybox/             # viewer.html
├── static/                # 프로젝트 공통 정적 파일
│   ├── accounts/          # 로그인 CSS/JS, 스프라이트
│   ├── kaixin/            # 관리자 CSS
│   └── mybox/             # 뷰어 CSS/JS · 기본 이미지 `images/viewer.jpg`
├── media/                 # 업로드 (`mybox/viewer`, `downloads/<id>/`, gitignore)
├── config/                # Django 설정 · URL
├── db.sqlite3             # SQLite DB (migrate 후 생성, gitignore)
├── manage.py
└── requirements.txt
```
