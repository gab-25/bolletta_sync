/**
 * Bolletta Sync web app.
 *
 * Receives JSON requests from bolletta_sync and writes invoices to Google Drive
 * and payment reminders to Google Tasks, running as the account that deployed it.
 *
 * Request body: {"secret": "...", "action": "...", ...payload}
 * Response body: {"ok": true, ...result} or {"ok": false, "error": "..."}
 *
 * The shared secret is read from the SECRET script property.
 */

var ACTIONS = {
  ping: ping,
  ensure_namespace: ensureNamespace,
  save_invoice: saveInvoice,
  set_expire_invoice: setExpireInvoice,
};

function doPost(e) {
  try {
    var request = JSON.parse(e.postData.contents);

    var secret = PropertiesService.getScriptProperties().getProperty("SECRET");
    if (!secret) {
      return jsonResponse({ ok: false, error: "SECRET script property is not set" });
    }
    if (request.secret !== secret) {
      return jsonResponse({ ok: false, error: "invalid secret" });
    }

    var handler = ACTIONS[request.action];
    if (!handler) {
      return jsonResponse({ ok: false, error: "unknown action: " + request.action });
    }

    // Serialize requests so that concurrent calls can't create duplicate folders or tasks.
    var lock = LockService.getScriptLock();
    lock.waitLock(30000);
    try {
      var result = handler(request);
      result.ok = true;
      return jsonResponse(result);
    } finally {
      lock.releaseLock();
    }
  } catch (err) {
    return jsonResponse({ ok: false, error: String(err && err.message ? err.message : err) });
  }
}

function jsonResponse(body) {
  return ContentService.createTextOutput(JSON.stringify(body)).setMimeType(ContentService.MimeType.JSON);
}

function requireFields(request, fields) {
  fields.forEach(function (field) {
    if (request[field] === undefined || request[field] === null || request[field] === "") {
      throw new Error("missing field: " + field);
    }
  });
}

function ping() {
  return {};
}

/**
 * Ensures the bollette/<year>/<namespace> folder and the task list exist.
 * Payload: namespace, year, tasklist_name.
 */
function ensureNamespace(request) {
  requireFields(request, ["namespace", "year", "tasklist_name"]);

  var bolletteFolder = findOrCreateFolder("bollette", null);
  var yearFolder = findOrCreateFolder(String(request.year), bolletteFolder);
  var namespaceFolder = findOrCreateFolder(request.namespace, yearFolder);

  return {
    folder_id: namespaceFolder.getId(),
    tasklist_id: findOrCreateTasklist(request.tasklist_name),
  };
}

/**
 * Uploads the invoice PDF to the given folder, unless a file with the same name exists.
 * Payload: folder_id, file_name, content (base64).
 */
function saveInvoice(request) {
  requireFields(request, ["folder_id", "file_name", "content"]);

  var folder = DriveApp.getFolderById(request.folder_id);
  var files = folder.getFilesByName(request.file_name);
  while (files.hasNext()) {
    var existing = files.next();
    if (!existing.isTrashed()) {
      return { file_id: existing.getId(), created: false };
    }
  }

  var blob = Utilities.newBlob(Utilities.base64Decode(request.content), "application/pdf", request.file_name);
  var file = folder.createFile(blob);

  return { file_id: file.getId(), created: true };
}

/**
 * Creates the payment task in the given task list, unless a task with the same title exists.
 * Payload: tasklist_id, title, due (RFC 3339), notes.
 */
function setExpireInvoice(request) {
  requireFields(request, ["tasklist_id", "title", "due"]);

  var pageToken = null;
  do {
    var page = Tasks.Tasks.list(request.tasklist_id, {
      showCompleted: true,
      showHidden: true,
      maxResults: 100,
      pageToken: pageToken,
    });
    var items = page.items || [];
    for (var i = 0; i < items.length; i++) {
      if (items[i].title === request.title) {
        return { task_id: items[i].id, created: false };
      }
    }
    pageToken = page.nextPageToken;
  } while (pageToken);

  var task = Tasks.Tasks.insert(
    { title: request.title, due: request.due, notes: request.notes || "" },
    request.tasklist_id
  );

  return { task_id: task.id, created: true };
}

function findOrCreateFolder(name, parent) {
  var folders = parent ? parent.getFoldersByName(name) : DriveApp.getFoldersByName(name);
  while (folders.hasNext()) {
    var folder = folders.next();
    if (!folder.isTrashed()) {
      return folder;
    }
  }
  return parent ? parent.createFolder(name) : DriveApp.createFolder(name);
}

function findOrCreateTasklist(title) {
  var pageToken = null;
  do {
    var page = Tasks.Tasklists.list({ maxResults: 100, pageToken: pageToken });
    var items = page.items || [];
    for (var i = 0; i < items.length; i++) {
      if (items[i].title === title) {
        return items[i].id;
      }
    }
    pageToken = page.nextPageToken;
  } while (pageToken);

  return Tasks.Tasklists.insert({ title: title }).id;
}
