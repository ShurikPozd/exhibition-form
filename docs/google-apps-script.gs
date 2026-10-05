/**
 * Google Apps Script: принимает POST-заявки от приложения и дописывает строки в таблицу.
 *
 * Установка (5 минут, без Google Cloud и OAuth):
 *   1. https://script.google.com → «Новый проект».
 *   2. Вставить этот код вместо содержимого Code.gs.
 *   3. Вписать свой секрет в SECRETS.SHEET_TOKEN (должен совпадать с GOOGLE_SHEET_SECRET в .env).
 *   4. Создать таблицу Google Sheets и открыть её: Файл → «Создать таблицу».
 *      Идентификатор файла (из адреса .../d/<ID>/edit) вписать в SPREADSHEET_ID.
 *   5. «Развернуть» → «Новое развёртывание» → тип «Веб-приложение» →
 *      «Выполнять от моего имени» → «Доступ: для всех». Разрешить доступ, если спросят.
 *   6. Скопировать адрес вида .../exec в .env проекта:
 *      GOOGLE_SHEET_WEBHOOK_URL=https://script.google.com/macros/s/AKfy.../exec
 *
 * Таблица создаётся автоматически: при пустом листе скрипт сам записывает шапку.
 *
 * Синхронизация в приложении best-effort: если вебхук недоступен, заявка всё равно лежит
 * в SQLite, а повтор — кнопкой «Повторить отправку в Google» в /admin.
 */

var SECRETS = {
  SHEET_TOKEN: 'ВСТАВЬТЕ_СЕКРЕТ_ИЗ_ENV',
  SPREADSHEET_ID: 'ВСТАВЬТЕ_ID_ТАБЛИЦЫ'
};

/* Порядок колонок совпадает с exporters.headers() в проекте.
   Проверить актуальный список: python -m tools.print_headers */
var HEADERS = [
  '№',
  'Дата и время',
  'Имя',
  'Компания',
  'Кто вы?',
  'Что интересует на стенде',
  'Интересующие направления',
  'Что интересует',
  'Телефон',
  'Email',
  'Выслать/сделать после выставки',
  'Согласие ПДн'
];

/**
 * POST от приложения: {"secret": "...", "row": ["...", ...]}.
 * @param {GoogleAppsScript.Events.PostEvent} e событие POST.
 * @returns {GoogleAppsScript.HTML.HtmlServiceOutput} ответ в JSON.
 */
function doPost(e) {
  var body = JSON.parse(e.postData.contents);

  if (body.secret !== SECRETS.SHEET_TOKEN) {
    return reply({ error: 'bad secret' }, 403);
  }
  if (!body.row || body.row.length === 0) {
    return reply({ error: 'empty row' }, 400);
  }

  var sheet = getSheet();
  if (sheet.getLastRow() === 0) {
    sheet.appendRow(HEADERS);
    sheet.setFrozenRows(1);
  }

  sheet.appendRow(body.row);
  SpreadsheetApp.flush();

  return reply({ ok: true, row: sheet.getLastRow() });
}

/**
 * GET — проверка, что вебхук жив (можно открыть в браузере).
 * @returns {GoogleAppsScript.HTML.HtmlServiceOutput} ответ в JSON.
 */
function doGet() {
  return reply({ ok: true, rows: getSheet().getLastRow() });
}

/**
 * Открывает таблицу по ID и возвращает первый лист.
 * @returns {GoogleAppsScript.Spreadsheet.SpreadsheetApp.Sheet} лист с заявками.
 */
function getSheet() {
  var book = SpreadsheetApp.openById(SECRETS.SPREADSHEET_ID);
  return book.getSheets()[0];
}

/**
 * Отвечает JSON со статус-кодом.
 * @param {Object} data тело ответа.
 * @param {number} code HTTP-статус.
 * @returns {GoogleAppsScript.HTML.HtmlServiceOutput} ответ.
 */
function reply(data, code) {
  return ContentService.createTextOutput(JSON.stringify(data))
    .setMimeType(ContentService.MimeType.JSON);
}
