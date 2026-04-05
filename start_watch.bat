@echo off
echo ========================================
echo  KeywordV2 - 스프레드시트 버튼 감지 모드
echo  (5분마다 체크 요청 확인)
echo  종료: Ctrl+C
echo ========================================
cd /d "%~dp0"
python main.py --watch
