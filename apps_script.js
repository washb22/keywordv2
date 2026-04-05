// ============================================
// Google Apps Script - KeywordV2
// ============================================
// 컬럼: A:키워드 B:글제목 C:URL D:이전순위 E:현재순위 F:변동 G:마지막확인

// ★ 여기에 Render 서버 URL과 API 키를 입력하세요
var SERVER_URL = 'https://keywordv2.onrender.com';
var API_KEY = '';  // 서버의 API_KEY 환경변수와 동일하게 설정

function onOpen() {
  var ui = SpreadsheetApp.getUi();
  ui.createMenu('🔍 키워드 관리')
    .addItem('✅ 전체 순위 확인', 'requestCheckAll')
    .addItem('👆 선택한 키워드만 확인', 'requestCheckSelected')
    .addSeparator()
    .addItem('📊 결과 서식 적용', 'applyFormatting')
    .addSeparator()
    .addItem('⏰ 매일 6시 자동 체크 설정', 'setupDailyTrigger')
    .addItem('⏰ 자동 체크 해제', 'removeDailyTrigger')
    .addSeparator()
    .addItem('🔄 시트 초기화', 'resetSheet')
    .addToUi();
}

function requestCheckAll() {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('키워드');
  if (!sheet) {
    SpreadsheetApp.getUi().alert('\'키워드\' 시트를 찾을 수 없습니다.');
    return;
  }

  var lastRow = sheet.getLastRow();
  var keywordCount = lastRow > 1 ? lastRow - 1 : 0;
  if (keywordCount === 0) {
    SpreadsheetApp.getUi().alert('키워드가 없습니다.');
    return;
  }

  var sheetName = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet().getName();

  try {
    var payload = { 'sheet_name': sheetName };
    var options = {
      'method': 'post',
      'headers': { 'X-API-Key': API_KEY, 'Content-Type': 'application/json' },
      'payload': JSON.stringify(payload),
      'muteHttpExceptions': true
    };
    var response = UrlFetchApp.fetch(SERVER_URL + '/check/all', options);
    var result = JSON.parse(response.getContentText());

    SpreadsheetApp.getUi().alert(
      '순위 확인 시작!\n\n' +
      '• 시트: ' + sheetName + '\n' +
      '• ' + result.message + '\n' +
      '• 잠시 후 결과가 업데이트됩니다.'
    );
  } catch (e) {
    SpreadsheetApp.getUi().alert('서버 연결 실패!\n\n' + e.message + '\n\n서버가 슬립 중일 수 있습니다. 30초 후 다시 시도해주세요.');
  }
}

function requestCheckSelected() {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('키워드');
  if (!sheet) {
    SpreadsheetApp.getUi().alert('\'키워드\' 시트를 찾을 수 없습니다.');
    return;
  }

  var selection = SpreadsheetApp.getActiveRange();
  var startRow = selection.getRow();
  var endRow = startRow + selection.getNumRows() - 1;

  if (startRow <= 1) {
    SpreadsheetApp.getUi().alert('키워드가 있는 행(2행 이하)을 선택해주세요.');
    return;
  }

  var keywords = [];
  for (var i = startRow; i <= endRow; i++) {
    var kw = sheet.getRange(i, 1).getValue();
    if (kw) keywords.push(kw);
  }

  if (keywords.length === 0) {
    SpreadsheetApp.getUi().alert('선택한 행에 키워드가 없습니다.');
    return;
  }

  var sheetName = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet().getName();

  try {
    var payload = { 'start_row': startRow, 'end_row': endRow, 'sheet_name': sheetName };
    var options = {
      'method': 'post',
      'headers': { 'X-API-Key': API_KEY, 'Content-Type': 'application/json' },
      'payload': JSON.stringify(payload),
      'muteHttpExceptions': true
    };
    var response = UrlFetchApp.fetch(SERVER_URL + '/check/selected', options);
    var result = JSON.parse(response.getContentText());

    SpreadsheetApp.getUi().alert(
      '선택 키워드 확인 시작!\n\n' +
      '• ' + keywords.join(', ') + '\n' +
      '• ' + result.message
    );
  } catch (e) {
    SpreadsheetApp.getUi().alert('서버 연결 실패!\n\n' + e.message);
  }
}

function applyFormatting() {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('키워드');
  if (!sheet) return;

  var lastRow = sheet.getLastRow();
  if (lastRow < 2) return;

  // 헤더
  var headerRange = sheet.getRange('A1:G1');
  headerRange.setBackground('#3366CC')
    .setFontColor('#FFFFFF')
    .setFontWeight('bold')
    .setFontSize(11)
    .setHorizontalAlignment('center');

  var dataRange = sheet.getRange(2, 1, lastRow - 1, 7);
  dataRange.setVerticalAlignment('middle');

  for (var i = 2; i <= lastRow; i++) {
    // 이전 순위 (D열)
    var prevRank = sheet.getRange(i, 4).getValue().toString();
    var prevRankCell = sheet.getRange(i, 4);
    prevRankCell.setHorizontalAlignment('center');
    if (prevRank.indexOf('미노출') >= 0) {
      prevRankCell.setBackground('#FFF').setFontColor('#999999');
    } else if (prevRank.indexOf('위') >= 0) {
      prevRankCell.setBackground('#FFF').setFontColor('#666666');
    }

    // 현재 순위 (E열)
    var status = sheet.getRange(i, 5).getValue().toString();
    var statusCell = sheet.getRange(i, 5);
    statusCell.setHorizontalAlignment('center');
    if (status.indexOf('미노출') >= 0) {
      statusCell.setBackground('#FFCDD2').setFontColor('#C62828');
    } else if (status.indexOf('1위') >= 0 || status.indexOf('2위') >= 0 || status.indexOf('3위') >= 0) {
      statusCell.setBackground('#C8E6C9').setFontColor('#1B5E20').setFontWeight('bold');
    } else if (status.indexOf('위') >= 0) {
      statusCell.setBackground('#E3F2FD').setFontColor('#1565C0');
    }

    // 변동 (F열)
    var change = sheet.getRange(i, 6).getValue().toString();
    var changeCell = sheet.getRange(i, 6);
    changeCell.setHorizontalAlignment('center');
    if (change.indexOf('▲') >= 0) {
      changeCell.setFontColor('#1B5E20').setFontWeight('bold');
    } else if (change.indexOf('▼') >= 0) {
      changeCell.setFontColor('#C62828').setFontWeight('bold');
    }
  }

  // 열 너비
  sheet.setColumnWidth(1, 150);  // 키워드
  sheet.setColumnWidth(2, 200);  // 글 제목
  sheet.setColumnWidth(3, 300);  // URL
  sheet.setColumnWidth(4, 120);  // 이전 순위
  sheet.setColumnWidth(5, 120);  // 현재 순위
  sheet.setColumnWidth(6, 70);   // 변동
  sheet.setColumnWidth(7, 140);  // 마지막 확인

  sheet.setFrozenRows(1);
  SpreadsheetApp.getUi().alert('서식 적용 완료!');
}

// === 매일 새벽 6시 자동 체크 (트리거용) ===
function dailyAutoCheck() {
  try {
    // 서버 깨우기 (슬립 상태일 수 있으므로)
    try { UrlFetchApp.fetch(SERVER_URL + '/health', { 'muteHttpExceptions': true }); } catch(e) {}
    Utilities.sleep(5000);

    // 모든 시트를 순회하며 체크 요청
    var sheets = SpreadsheetApp.getActiveSpreadsheet().getSheets();
    for (var i = 0; i < sheets.length; i++) {
      var sheetName = sheets[i].getName();
      var lastRow = sheets[i].getLastRow();
      if (lastRow < 2) continue;  // 데이터 없는 시트 스킵

      var payload = { 'sheet_name': sheetName };
      var options = {
        'method': 'post',
        'headers': { 'X-API-Key': API_KEY, 'Content-Type': 'application/json' },
        'payload': JSON.stringify(payload),
        'muteHttpExceptions': true
      };
      var response = UrlFetchApp.fetch(SERVER_URL + '/check/all', options);
      console.log('[' + sheetName + '] 체크 요청: ' + response.getContentText());

      // 이전 시트 체크가 끝날 때까지 대기
      Utilities.sleep(10000);
      _waitForCheckComplete();
    }
  } catch (e) {
    console.log('자동 체크 실패: ' + e.message);
  }
}

function _waitForCheckComplete() {
  // 서버가 체크 완료할 때까지 대기 (최대 30분)
  for (var i = 0; i < 60; i++) {
    Utilities.sleep(30000);  // 30초마다 확인
    try {
      var resp = UrlFetchApp.fetch(SERVER_URL + '/health', { 'muteHttpExceptions': true });
      var data = JSON.parse(resp.getContentText());
      if (!data.checking) return;
    } catch(e) {}
  }
}

// === 자동 체크 트리거 설정/해제 ===
function setupDailyTrigger() {
  // 기존 트리거 삭제
  var triggers = ScriptApp.getProjectTriggers();
  for (var i = 0; i < triggers.length; i++) {
    if (triggers[i].getHandlerFunction() === 'dailyAutoCheck') {
      ScriptApp.deleteTrigger(triggers[i]);
    }
  }
  // 매일 새벽 6시 트리거 생성
  ScriptApp.newTrigger('dailyAutoCheck')
    .timeBased()
    .atHour(6)
    .everyDays(1)
    .inTimezone('Asia/Seoul')
    .create();

  SpreadsheetApp.getUi().alert('매일 새벽 6시 자동 체크가 설정되었습니다!');
}

function removeDailyTrigger() {
  var triggers = ScriptApp.getProjectTriggers();
  var count = 0;
  for (var i = 0; i < triggers.length; i++) {
    if (triggers[i].getHandlerFunction() === 'dailyAutoCheck') {
      ScriptApp.deleteTrigger(triggers[i]);
      count++;
    }
  }
  SpreadsheetApp.getUi().alert('자동 체크 트리거 ' + count + '개 삭제 완료');
}

function resetSheet() {
  var ui = SpreadsheetApp.getUi();
  var response = ui.alert(
    '시트 초기화',
    '모든 데이터가 삭제되고 헤더만 남습니다.\n정말 초기화하시겠습니까?',
    ui.ButtonSet.YES_NO
  );
  if (response !== ui.Button.YES) return;

  var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('키워드');
  if (!sheet) {
    sheet = SpreadsheetApp.getActiveSpreadsheet().insertSheet('키워드');
  }

  sheet.clear();
  var headers = ['키워드', '글 제목', 'URL', '이전 순위', '현재 순위', '변동', '마지막 확인'];
  sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  applyFormatting();
  ui.alert('초기화 완료!\n\nA~C열에 키워드 정보를 입력하세요.');
}
