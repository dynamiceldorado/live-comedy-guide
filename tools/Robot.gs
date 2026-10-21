/**
 * Comedy Database robot — pushes the sheet to GitHub so both sites rebuild themselves.
 * Paste this whole file into Extensions > Apps Script in the "Comedy Database — Guide + Directory" sheet.
 *
 * Menu "Robot" (appears after reload):
 *   1. Set GitHub token   — paste the token once. It is stored privately in this script, never in a cell.
 *   2. Run setup          — adds the date_text column and a Shows section row if missing, and turns on the hourly push.
 *   3. Publish now        — files the inbox and pushes right away instead of waiting for the hourly run.
 *
 * INBOX: Claude's scheduled tasks cannot write to this sheet directly. They drop JSON files whose
 * names start with "sheet-inbox" in the Drive folder "Live Comedy — Claude files". Every hour the
 * robot files them here (Events upserted by id; Directory Queue and Resources appended when the id
 * is new), logs what it did on the "Robot log" tab, and moves each file to "inbox processed".
 * Miguel's cells win: rejected rows are never touched, and ded_pick, pick_note, image_url and
 * internal_note are never overwritten on an existing row.
 *
 * Only public columns of the Events tab leave the sheet (internal_note, source, first_seen,
 * last_verified, out_of_town and price_max_usd stay private). Nothing is pushed when nothing changed.
 */

var OWNER = 'dynamiceldorado';
var GUIDE = 'live-comedy-guide';
var DIRECTORY = 'atlanta-comedy-directory';

var EVENT_COLUMNS = ['id', 'status', 'view', 'cheap_date', 'type', 'genre', 'tier', 'title',
  'start_date', 'end_date', 'date_text', 'time', 'venue', 'area', 'price_text', 'link',
  'description', 'image_url', 'ded_pick', 'pick_note'];
var INBOX_FOLDER = '1Mzbm7NiM8hUPl4cjCbH3vx8KFwnK_lWk';
var PROTECTED = ['ded_pick', 'pick_note', 'image_url', 'internal_note', 'first_seen'];
var SECTION_COLUMNS = ['section_key', 'display_order', 'title', 'active', 'notes'];

function onOpen() {
  SpreadsheetApp.getUi().createMenu('Robot')
    .addItem('1. Set GitHub token', 'setToken')
    .addItem('2. Run setup', 'setup')
    .addItem('3. Publish now', 'publishNowWithMessage')
    .addToUi();
}

function setToken() {
  var ui = SpreadsheetApp.getUi();
  var r = ui.prompt('GitHub token', 'Paste the fine-grained token (starts with github_pat_).', ui.ButtonSet.OK_CANCEL);
  if (r.getSelectedButton() !== ui.Button.OK) return;
  var t = r.getResponseText().trim();
  if (t.indexOf('github_pat_') !== 0) { ui.alert('That does not look like a fine-grained token. Nothing saved.'); return; }
  PropertiesService.getScriptProperties().setProperty('GITHUB_TOKEN', t);
  ui.alert('Token saved. Next: Robot > 2. Run setup.');
}

function setup() {
  var ss = SpreadsheetApp.getActive();
  var notes = [];

  // date_text column on Events (free-text dates like "Late Feb 2027"), backfilled from the live Guide.
  var ev = ss.getSheetByName('Events');
  var head = ev.getRange(1, 1, 1, ev.getLastColumn()).getValues()[0];
  if (head.indexOf('date_text') === -1) {
    var after = head.indexOf('end_date') + 1;
    ev.insertColumnAfter(after);
    ev.getRange(1, after + 1).setValue('date_text');
    var fill = {
      '20261019-dg-university': 'Underway', '20261130-westend': 'By Nov 30',
      '20261121-clowns-of-steel': 'Sat Nov 21 (4 Saturdays)', '20270222-eric-davis': 'Late Feb 2027',
      '20270801-countdown': 'Aug 2027 (TBA)', '20271001-secret-city': 'Oct 2027 (TBA)'
    };
    var ids = ev.getRange(2, 1, Math.max(ev.getLastRow() - 1, 1), 1).getValues();
    for (var i = 0; i < ids.length; i++) {
      if (fill[ids[i][0]]) ev.getRange(i + 2, after + 1).setValue(fill[ids[i][0]]);
    }
    notes.push('Added a date_text column to Events.');
  }

  // Directory needs a Shows section row (Shows first).
  var sec = ss.getSheetByName('Sections & Tags');
  var keys = sec.getRange(2, 1, Math.max(sec.getLastRow() - 1, 1), 1).getValues().map(function (r) { return String(r[0]).trim(); });
  if (keys.indexOf('show') === -1) {
    var row = keys.indexOf('') === -1 ? keys.length + 2 : keys.indexOf('') + 2;
    sec.getRange(row, 1, 1, 5).setValues([['show', 0, 'Shows', 'Y', 'Directory: shows by next show date']]);
    notes.push('Added a Shows row to Sections & Tags.');
  }

  // Hourly push (skips when nothing changed).
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'publishNow') ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger('publishNow').timeBased().everyHours(1).create();
  notes.push('Hourly push is on.');

  SpreadsheetApp.getUi().alert(notes.join('\n') + '\n\nNext: Robot > 3. Publish now.');
}

function publishNowWithMessage() {
  var res = publishNow();
  SpreadsheetApp.getUi().alert(res.join('\n') + '\n\nThe sites update a minute or two after a push.');
}

function publishNow() {
  var ss = SpreadsheetApp.getActive();
  var filed = processInbox(ss);
  var events = tabCsv(ss, 'Events', EVENT_COLUMNS);
  var sections = tabCsv(ss, 'Sections & Tags', SECTION_COLUMNS);
  var listings = tabCsv(ss, 'Listings', null);
  return filed.concat([
    push(GUIDE, 'data/sheet/events.csv', events),
    push(GUIDE, 'data/sheet/sections.csv', sections),
    push(DIRECTORY, 'data/listings.csv', listings),
    push(DIRECTORY, 'data/sections.csv', sections)
  ]);
}

// ---------- inbox ----------
function processInbox(ss) {
  var folder = DriveApp.getFolderById(INBOX_FOLDER);
  var files = folder.searchFiles("title contains 'sheet-inbox' and trashed = false");
  var done = getOrMakeFolder(folder, 'inbox processed');
  var out = [];
  var list = [];
  while (files.hasNext()) list.push(files.next());
  list.sort(function (a, b) { return a.getDateCreated() - b.getDateCreated(); });
  list.forEach(function (f) {
    var msg;
    try {
      var data = JSON.parse(f.getBlob().getDataAsString('UTF-8'));
      var e = upsertEvents(ss, data.events || []);
      var q = appendNew(ss, 'Directory Queue', data.directory_queue || []);
      var r = appendNew(ss, 'Resources', data.resources || []);
      msg = f.getName() + ': events ' + e.added + ' added, ' + e.updated + ' updated, ' + e.skipped + ' skipped (yours); queue +' + q + '; resources +' + r;
      f.moveTo(done);
    } catch (err) {
      msg = f.getName() + ': NOT FILED, ' + err.message;
      f.setName('FAILED ' + f.getName());
    }
    log(ss, msg);
    out.push(msg);
  });
  return out.length ? out : ['inbox: empty'];
}

function upsertEvents(ss, rows) {
  var sh = ss.getSheetByName('Events');
  var vals = sh.getDataRange().getValues();
  var head = vals[0].map(function (h) { return String(h).trim(); });
  var col = function (name) { return head.indexOf(name); };
  var byId = {};
  for (var i = 1; i < vals.length; i++) if (vals[i][0]) byId[String(vals[i][0]).trim()] = i;
  var today = Utilities.formatDate(new Date(), 'America/New_York', 'yyyy-MM-dd');
  var res = { added: 0, updated: 0, skipped: 0 };
  rows.forEach(function (r) {
    if (!r.id) return;
    var i = byId[r.id];
    if (i === undefined) {
      var row = head.map(function (h) { return r[h] !== undefined ? asText(r[h]) : ''; });
      if (col('first_seen') > -1 && !row[col('first_seen')]) row[col('first_seen')] = asText(today);
      if (col('last_verified') > -1) row[col('last_verified')] = asText(r.last_verified || today);
      sh.appendRow(row);
      byId[r.id] = sh.getLastRow() - 1;
      res.added++;
      return;
    }
    var cur = vals[i];
    if (String(cur[col('status')]).trim().toLowerCase() === 'rejected') { res.skipped++; return; }
    Object.keys(r).forEach(function (k) {
      var c = col(k);
      if (c < 0 || k === 'id') return;
      if (PROTECTED.indexOf(k) > -1 && String(cur[c]).trim() !== '') return;
      sh.getRange(i + 1, c + 1).setValue(asText(r[k]));
    });
    if (col('last_verified') > -1) sh.getRange(i + 1, col('last_verified') + 1).setValue(asText(r.last_verified || today));
    res.updated++;
  });
  return res;
}

function appendNew(ss, tab, rows) {
  if (!rows.length) return 0;
  var sh = ss.getSheetByName(tab);
  var vals = sh.getDataRange().getValues();
  var head = vals[0].map(function (h) { return String(h).trim(); });
  var ids = {};
  for (var i = 1; i < vals.length; i++) ids[String(vals[i][0]).trim()] = true;
  var n = 0;
  rows.forEach(function (r) {
    if (!r.id || ids[r.id]) return;
    sh.appendRow(head.map(function (h) { return r[h] !== undefined ? asText(r[h]) : ''; }));
    ids[r.id] = true;
    n++;
  });
  return n;
}

// Keep dates, times and prices exactly as written (Sheets would otherwise turn "2026-11-20" into a date).
function asText(v) {
  v = v === null || v === undefined ? '' : String(v);
  return /^[\d$+=@-]/.test(v) ? "'" + v : v;
}

function log(ss, msg) {
  var sh = ss.getSheetByName('Robot log') || ss.insertSheet('Robot log');
  if (sh.getLastRow() === 0) sh.appendRow(['when', 'what']);
  sh.appendRow([Utilities.formatDate(new Date(), 'America/New_York', 'yyyy-MM-dd HH:mm'), msg]);
}

function getOrMakeFolder(parent, name) {
  var it = parent.getFoldersByName(name);
  return it.hasNext() ? it.next() : parent.createFolder(name);
}

// One tab as CSV, using what the cells display (so "8:00 PM" stays "8:00 PM").
function tabCsv(ss, name, columns) {
  var sh = ss.getSheetByName(name);
  if (!sh) throw new Error('Tab not found: ' + name);
  var vals = sh.getDataRange().getDisplayValues();
  var head = vals[0].map(function (h) { return String(h).trim(); });
  var idx = columns ? columns.map(function (c) { return head.indexOf(c); }) : head.map(function (_, i) { return i; });
  if (columns) {
    var missing = columns.filter(function (c, i) { return idx[i] === -1 && c !== 'date_text'; });
    if (missing.length) throw new Error(name + ' tab is missing columns: ' + missing.join(', '));
  }
  var out = [columns || head];
  for (var r = 1; r < vals.length; r++) {
    if (!String(vals[r][0]).trim()) continue;
    out.push(idx.map(function (i) { return i === -1 ? '' : vals[r][i]; }));
  }
  return out.map(function (row) {
    return row.map(function (v) {
      v = String(v);
      return /[",\n\r]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v;
    }).join(',');
  }).join('\n') + '\n';
}

function push(repo, path, text) {
  var token = PropertiesService.getScriptProperties().getProperty('GITHUB_TOKEN');
  if (!token) throw new Error('No GitHub token. Use Robot > 1. Set GitHub token.');
  var url = 'https://api.github.com/repos/' + OWNER + '/' + repo + '/contents/' + path;
  var headers = { Authorization: 'Bearer ' + token, Accept: 'application/vnd.github+json' };
  var b64 = Utilities.base64Encode(text, Utilities.Charset.UTF_8);

  var sha = null;
  var get = UrlFetchApp.fetch(url + '?ref=main', { headers: headers, muteHttpExceptions: true });
  if (get.getResponseCode() === 200) {
    var cur = JSON.parse(get.getContentText());
    sha = cur.sha;
    if (String(cur.content).replace(/\s/g, '') === b64) return repo + '/' + path + ': no change';
  } else if (get.getResponseCode() !== 404) {
    throw new Error(repo + '/' + path + ': GitHub said ' + get.getResponseCode() + ' ' + get.getContentText());
  }

  var body = { message: 'Sheet sync ' + Utilities.formatDate(new Date(), 'America/New_York', 'yyyy-MM-dd HH:mm'), content: b64, branch: 'main' };
  if (sha) body.sha = sha;
  var put = UrlFetchApp.fetch(url, { method: 'put', headers: headers, contentType: 'application/json',
    payload: JSON.stringify(body), muteHttpExceptions: true });
  if (put.getResponseCode() >= 300) {
    throw new Error(repo + '/' + path + ': push failed ' + put.getResponseCode() + ' ' + put.getContentText());
  }
  return repo + '/' + path + ': pushed';
}
