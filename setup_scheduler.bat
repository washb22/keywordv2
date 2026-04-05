@echo off
echo ========================================
echo  KeywordV2 - 매일 오전 9시 자동 실행 등록
echo ========================================
echo.

:: 작업 스케줄러에 등록
schtasks /create /tn "KeywordV2_DailyCheck" /tr "python \"%~dp0main.py\"" /sc daily /st 09:00 /f

if %errorlevel% == 0 (
    echo.
    echo [성공] 매일 오전 9시에 자동 순위 체크가 실행됩니다.
    echo.
    echo 확인: 작업 스케줄러에서 "KeywordV2_DailyCheck" 검색
    echo 삭제: schtasks /delete /tn "KeywordV2_DailyCheck" /f
) else (
    echo.
    echo [실패] 관리자 권한으로 다시 실행해주세요.
    echo 이 파일을 우클릭 → "관리자 권한으로 실행"
)
echo.
pause
