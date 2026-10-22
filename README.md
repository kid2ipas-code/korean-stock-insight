# 한국 주식 타이밍 분석

초보자용 Streamlit 웹앱입니다. KRX 종목 목록에서 KOSPI·KOSDAQ 전체 종목을 하루 한 번 받아오며, 종목명 또는 6자리 종목코드를 입력하면 약 5년의 일봉 데이터를 요청하고 최근 12개월을 중심으로 이동평균, RSI, MACD, 거래량, 볼린저 밴드, ATR과 규칙 기반 판단을 표시합니다.

## Windows 11 실행

PowerShell에서 이 폴더로 이동한 뒤 처음 한 번만 실행합니다.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run app.py
```

브라우저에서 `http://localhost:8501`을 엽니다. 실행 정책 때문에 활성화가 막히면 `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`를 한 번 실행한 뒤 다시 시도합니다.

## 매일 자동 실행

`start_app.ps1`은 프로그램 폴더와 가상환경을 자동으로 찾아 Streamlit을 실행합니다. Windows 로그인 때 자동으로 시작하도록 설정하면 브라우저에서 `http://localhost:8501`을 열 때마다 앱을 사용할 수 있습니다.

## 데이터 주의

종목 목록은 FinanceDataReader를 통해 KRX 목록을 조회하고, 가격 데이터는 Yahoo Finance를 통한 무료 보조 데이터로 작동합니다. KRX 공식 Open API는 회원가입과 인증키가 필요하므로 아직 가격 데이터 소스로 연결하지 않았습니다. 무료 데이터는 지연·누락·수정 가능성이 있으며 투자 판단과 백테스트의 미래 성과를 보장하지 않습니다.

## 다음 단계

1. KRX Open API 인증키를 발급받아 공식 데이터 우선·Yahoo 대조 기능 추가
2. 점수 가중치와 임계값을 설정 파일로 실제 연결
3. 거래비용·세금·슬리피지·다음 거래일 체결을 포함한 워크포워드 백테스트 추가
4. 종목명 검색 목록과 데이터 출처 로그 저장 추가
