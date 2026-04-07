// ============================================
// Google Apps Script - KeywordV2 (로컬 Watch 모드)
// ============================================
// 컬럼: A:키워드 B:글제목 C:URL D:이전순위 E:현재순위 F:변동 G:마지막확인 H:체크요청플래그
//
// 로컬 PC에서 python main.py --watch 가 실행 중이어야 합니다.
// Apps Script는 HTTP 요청 대신 시트 H1 셀에 '체크 요청' 문자열을 기록하고,
// 로컬 watch 모드가 1분마다 감지하여 체크를 수행합니다.

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
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  var sheetName = sheet.getName();

  var lastRow = sheet.getLastRow();
  var keywordCount = lastRow > 1 ? lastRow - 1 : 0;
  if (keywordCount === 0) {
    SpreadsheetApp.getUi().alert('키워드가 없습니다.');
    return;
  }

  // H1 셀에 "체크 요청" 기록 - 로컬 watch 모드가 1분 안에 감지합니다
  try {
    sheet.getRange('H1').setValue('체크 요청');
    SpreadsheetApp.getUi().alert(
      '✅ 체크 요청 전송!\n\n' +
      '• 시트: ' + sheetName + '\n' +
      '• 키워드: ' + keywordCount + '개\n' +
      '• 로컬 PC에서 1분 내 처리됩니다.\n' +
      '• 본인 PC가 켜져 있어야 작동합니다.'
    );
  } catch (e) {
    SpreadsheetApp.getUi().alert('H1 셀 쓰기 실패: ' + e.message);
  }
}

function requestCheckSelected() {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  var sheetName = sheet.getName();

  var selection = SpreadsheetApp.getActiveRange();
  var startRow = selection.getRow();
  var endRow = startRow + selection.getNumRows() - 1;

  if (startRow <= 1) {
    SpreadsheetApp.getUi().alert('키워드가 있는 행(2행 이하)을 선택해주세요.');
    return;
  }

  var keywords = [];
  var validStartRow = startRow;
  var validEndRow = startRow;
  for (var i = startRow; i <= endRow; i++) {
    var kw = sheet.getRange(i, 1).getValue();
    if (kw && kw.toString().trim() !== '') {
      keywords.push(kw.toString().trim());
      validEndRow = i;
    }
  }

  if (keywords.length === 0) {
    SpreadsheetApp.getUi().alert('선택한 행에 키워드가 없습니다.');
    return;
  }

  // H1 셀에 "체크:시작행-끝행" 기록
  try {
    var flag = '체크:' + validStartRow + '-' + validEndRow;
    sheet.getRange('H1').setValue(flag);
    SpreadsheetApp.getUi().alert(
      '✅ 선택 체크 요청 전송!\n\n' +
      '• 키워드: ' + keywords.join(', ') + '\n' +
      '• 행: ' + validStartRow + '~' + validEndRow + '\n' +
      '• 로컬 PC에서 1분 내 처리됩니다.'
    );
  } catch (e) {
    SpreadsheetApp.getUi().alert('H1 셀 쓰기 실패: ' + e.message);
  }
}

function applyFormatting() {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();

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
// 모든 시트의 H1 셀에 '체크 요청' 기록. 로컬 watch 모드가 1분 안에 감지하여 순차 처리.
function dailyAutoCheck() {
  try {
    var sheets = SpreadsheetApp.getActiveSpreadsheet().getSheets();
    var flagged = 0;
    for (var i = 0; i < sheets.length; i++) {
      var sheetName = sheets[i].getName();
      var lastRow = sheets[i].getLastRow();
      if (lastRow < 2) continue;  // 데이터 없는 시트 스킵
      try {
        sheets[i].getRange('H1').setValue('체크 요청');
        console.log('[' + sheetName + '] H1 플래그 기록');
        flagged++;
      } catch (err) {
        console.log('[' + sheetName + '] H1 쓰기 실패: ' + err.message);
      }
    }
    console.log('총 ' + flagged + '개 시트에 체크 요청 플래그 기록 완료');
  } catch (e) {
    console.log('자동 체크 실패: ' + e.message);
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

  var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();

  sheet.clear();
  var headers = ['키워드', '글 제목', 'URL', '이전 순위', '현재 순위', '변동', '마지막 확인'];
  sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  applyFormatting();
  ui.alert('\'' + sheet.getName() + '\' 시트 초기화 완료!\n\nA~C열에 키워드 정보를 입력하세요.');
}
