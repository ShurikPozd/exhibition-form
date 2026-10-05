/* Клиентская логика анкеты: подсказки под полями, мягкое форматирование телефона,
   сбор данных, проверки до отправки, черновик в localStorage и экран «Спасибо».

   Проверки здесь — только для удобства: всё равно всё проверяется на сервере
   (schemas.py → utils/validators.py), поэтому правила повторяют серверные, а не наоборот. */

(function () {
  "use strict";

  var ENDPOINT = "/api/submissions";
  var DRAFT_KEY = "exhibition-form-draft-v1";
  var CHECK_GROUPS = ["role", "stall", "directions", "interest"];
  var TEXT_KEYS = ["name", "company", "role_other", "phone", "email", "after_show"];
  var EMAIL_RE = /^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$/;
  var PHONE_DIGITS_MIN = 10;
  var PHONE_DIGITS_MAX = 15;
  /* Сколько секунд висит экран «Спасибо», прежде чем форма очистится для следующего посетителя */
  var RESET_SECONDS = 3;

  /* Переводы приезжают вместе со страницей в теге script с типом application/json,
     поэтому отдельный файл с языками не нужен и клиент не знает про сервер.
     Если словаря нет (страница собрана без перевода), подсказки просто молчат. */
  var MESSAGES = readMessages();
  var SERVER_MESSAGES = MESSAGES.server || {};

  function readMessages() {
    var node = document.getElementById("i18n");
    if (!node) {
      return { js: {} };
    }
    try {
      var parsed = JSON.parse(node.textContent || "{}");
      return { js: parsed.js || {}, server: parsed.server || {} };
    } catch (err) {
      return { js: {}, server: {} };
    }
  }

  function t(key, params) {
    var text = MESSAGES.js[key] || "";
    Object.keys(params || {}).forEach(function (name) {
      text = text.split("{" + name + "}").join(params[name]);
    });
    return text;
  }

  /* Сообщения сервера раскладываются по полям, чтобы подсказка появилась под нужным полем */
  var PROBLEM_FIELDS = [
    [/телефон или email/i, "phone"],
    [/согласие/i, "consent"],
    [/другое/i, "role_other"],
    [/имя/i, "name"],
    [/почт/i, "email"],
    [/email/i, "email"],
    [/телефон/i, "phone"],
  ];

  var form = document.getElementById("lead-form");
  var done = document.getElementById("done");
  var doneId = document.getElementById("done-id");
  var doneNext = document.getElementById("done-next");
  var againBtn = document.getElementById("again");
  var status = document.getElementById("status");
  var submitBtn = document.getElementById("submit-btn");
  var resetTimer = null;

  function byKey(key) {
    return document.getElementById("f-" + key);
  }

  /* Имя поля из id контрола: f-phone → phone. У чекбоксов id вида f-role-c1-0. */
  function keyOf(node) {
    if (!node || !node.id || node.id.indexOf("f-") !== 0) {
      return "";
    }
    return node.id.slice(2);
  }

  function digitsOnly(value) {
    return (String(value || "").match(/\d/g) || []).join("");
  }

  function digitsOf(value) {
    return digitsOnly(value).length;
  }

  function setHint(key, text, kind) {
    var node = document.getElementById("hint-" + key);
    if (!node) {
      return;
    }
    node.textContent = text || "";
    node.className = text ? (kind ? "hint hint--" + kind : "hint") : "hint";
  }

  function setStatus(text, kind) {
    status.textContent = text;
    status.className = kind ? "status status--" + kind : "status";
  }

  function clearInvalid() {
    form.querySelectorAll(".is-invalid").forEach(function (node) {
      node.classList.remove("is-invalid");
    });
  }

  /* Число уже содержит код страны (7 или 8) — значит это российский или казахский
     номер, и его можно привести к привычному виду. */
  function looksRussian(raw, digits) {
    if (raw.charAt(0) === "+") {
      return digits.charAt(0) === "7";
    }
    return /^\s*[^\d]*[78]/.test(raw);
  }

  /* Мягкое форматирование: ничего не запрещаем и не додумываем.
     Приводим к виду только российский номер, который посетитель уже набрал
     с кодом страны (7 или 8). Номер другой страны остаётся ровно как введён —
     угадать страну по цифрам невозможно, а испорченный номер хуже некрасивого. */
  function formatPhone(value) {
    var raw = String(value || "").trim();
    if (!raw) {
      return "";
    }
    var digits = digitsOnly(raw);
    if (digits.length !== 11 || !looksRussian(raw, digits)) {
      return raw;
    }
    if (digits.charAt(0) === "8") {
      digits = "7" + digits.slice(1);
    }
    return (
      "+7 (" +
      digits.slice(1, 4) +
      ") " +
      digits.slice(4, 7) +
      "-" +
      digits.slice(7, 9) +
      "-" +
      digits.slice(9, 11)
    );
  }

  function checkPhone() {
    var phone = byKey("phone");
    if (!phone) {
      return;
    }
    var raw = phone.value.trim();
    var email = byKey("email");
    if (!raw) {
      setHint("phone", email && email.value.trim() ? "" : t("contact_required"), "info");
      return;
    }
    if (/[^\d\s()+.\-]/.test(raw)) {
      setHint("phone", t("foreign_chars"), "error");
      return;
    }
    var count = digitsOf(raw);
    if (count < PHONE_DIGITS_MIN) {
      setHint("phone", t("phone_digits_few", { count: count, min: PHONE_DIGITS_MIN }), "info");
    } else if (count > PHONE_DIGITS_MAX) {
      setHint("phone", t("phone_digits_many", { count: count, max: PHONE_DIGITS_MAX }), "error");
    } else if (!looksRussian(raw, digitsOnly(raw))) {
      setHint("phone", t("phone_foreign", { count: count }), "info");
    } else {
      setHint("phone", t("phone_ok", { count: count }), "ok");
    }
  }

  function checkEmail() {
    var email = byKey("email");
    if (!email) {
      return;
    }
    var raw = email.value.trim();
    if (!raw) {
      var phone = byKey("phone");
      setHint("email", phone && phone.value.trim() ? "" : t("contact_required_email"), "info");
      return;
    }
    if (EMAIL_RE.test(raw)) {
      setHint("email", t("email_ok"), "ok");
    } else {
      setHint("email", t("email_invalid"), "error");
    }
  }

  /* Возвращает первое поле с ошибкой или null, если всё заполнено верно. */
  function validate() {
    var name = byKey("name");
    var phone = byKey("phone");
    var email = byKey("email");
    var consent = byKey("consent");
    var phoneFilled = Boolean(phone.value.trim());
    var emailFilled = Boolean(email.value.trim());
    var firstBad = null;

    if (!name.value.trim()) {
      setHint("name", t("name_required"), "error");
      firstBad = firstBad || name;
    } else {
      setHint("name", "");
    }

    if (!phoneFilled && !emailFilled) {
      setHint("phone", t("contact_required_submit"), "error");
      firstBad = firstBad || phone;
    } else if (phoneFilled) {
      var count = digitsOf(phone.value);
      if (count < PHONE_DIGITS_MIN) {
        setHint("phone", t("phone_short", { count: count }), "error");
        firstBad = firstBad || phone;
      } else if (count > PHONE_DIGITS_MAX) {
        setHint("phone", t("phone_long", { count: count }), "error");
        firstBad = firstBad || phone;
      } else {
        setHint("phone", "");
      }
    } else {
      setHint("phone", "");
    }

    if (emailFilled && !EMAIL_RE.test(email.value.trim())) {
      setHint("email", t("email_invalid"), "error");
      firstBad = firstBad || email;
    } else {
      setHint("email", "");
    }

    if (!consent.checked) {
      setHint("consent", t("consent_required"), "error");
      firstBad = firstBad || consent;
    } else {
      setHint("consent", "");
    }

    return firstBad;
  }

  /* Собирает FormData в объект: группы чекбоксов становятся массивами. */
  function collect() {
    var payload = {};
    var data = new FormData(form);

    TEXT_KEYS.forEach(function (key) {
      var node = byKey(key);
      payload[key] = node ? node.value.trim() : "";
    });
    CHECK_GROUPS.forEach(function (key) {
      payload[key] = data.getAll(key).map(String);
    });
    payload.consent = byKey("consent").checked;
    return payload;
  }

  function saveDraft() {
    try {
      window.localStorage.setItem(DRAFT_KEY, JSON.stringify(collect()));
    } catch (err) {
      /* приватный режим iPad не даёт доступ к localStorage — это не повод мешать заполнению */
    }
  }

  function restoreDraft() {
    var raw;
    try {
      raw = window.localStorage.getItem(DRAFT_KEY);
    } catch (err) {
      return;
    }
    if (!raw) {
      return;
    }

    var draft;
    try {
      draft = JSON.parse(raw);
    } catch (err) {
      return;
    }
    if (!draft) {
      return;
    }

    TEXT_KEYS.forEach(function (key) {
      var node = byKey(key);
      if (node && typeof draft[key] === "string") {
        node.value = draft[key];
      }
    });
    CHECK_GROUPS.forEach(function (key) {
      var chosen = Array.isArray(draft[key]) ? draft[key] : [];
      form.querySelectorAll('input[name="' + key + '"]').forEach(function (input) {
        input.checked = chosen.indexOf(input.value) !== -1;
      });
    });
    if (draft.consent) {
      byKey("consent").checked = true;
    }
    setStatus(t("draft_restored"), "ok");
  }

  function clearDraft() {
    try {
      window.localStorage.removeItem(DRAFT_KEY);
    } catch (err) {
      /* см. saveDraft */
    }
  }

  function stopResetTimer() {
    if (resetTimer) {
      window.clearInterval(resetTimer);
      resetTimer = null;
    }
  }

  /* Очищает форму для следующего посетителя стенда. */
  function resetToBlank() {
    stopResetTimer();
    form.reset();
    clearInvalid();
    TEXT_KEYS.concat(["consent"]).forEach(function (key) {
      setHint(key, "");
    });
    clearDraft();
    setStatus("");
    done.hidden = true;
    form.hidden = false;
    byKey("name").focus();
  }

  function showDone(id) {
    form.hidden = true;
    doneId.textContent = String(id);
    done.hidden = false;
    window.scrollTo({ top: 0, behavior: "smooth" });

    var left = RESET_SECONDS;
    doneNext.textContent = t("done_next", { seconds: left });
    stopResetTimer();
    resetTimer = window.setInterval(function () {
      left -= 1;
      if (left > 0) {
        doneNext.textContent = t("done_next", { seconds: left });
        return;
      }
      resetToBlank();
    }, 1000);
  }

  /* Разбирает 422: подсказки ставим под конкретные поля, в статус — первое сообщение. */
  function applyServerProblems(detail) {
    if (!Array.isArray(detail) || !detail.length) {
      return t("status_generic");
    }
    var summary = "";
    detail.forEach(function (item) {
      /* Pydantic добавляет служебное "Value error, " — убираем его */
      var message = String(item.msg || "").replace(/^Value error,\s*/, "") || t("status_fields");
      var key = Array.isArray(item.loc) && item.loc.length > 1 ? String(item.loc[item.loc.length - 1]) : "";
      if (!key) {
        PROBLEM_FIELDS.forEach(function (pair) {
          if (!key && pair[0].test(message)) {
            key = pair[1];
          }
        });
      }
      /* Ответ сервера приходит на языке по умолчанию: подсказываем посетителю
         перевод по ключу поля, а если перевода нет — показываем ответ как есть. */
      message = SERVER_MESSAGES[key] || message;
      summary = summary || message;
      if (key) {
        setHint(key, message, "error");
        var node = byKey(key);
        if (node) {
          node.classList.add("is-invalid");
        }
      }
    });
    return summary;
  }

  function send(payload) {
    submitBtn.disabled = true;
    setStatus(t("status_sending"));

    fetch(ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
      .then(function (response) {
        return response
          .json()
          .catch(function () {
            return {};
          })
          .then(function (data) {
            return { ok: response.ok, data: data };
          });
      })
      .then(function (result) {
        if (result.ok) {
          clearDraft();
          showDone(result.data.id);
          return;
        }
        setStatus(applyServerProblems(result.data.detail), "error");
        submitBtn.disabled = false;
      })
      .catch(function (err) {
        setStatus(t("status_offline"), "error");
        submitBtn.disabled = false;
      });
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    clearInvalid();

    var bad = validate();
    if (bad) {
      bad.focus();
      setStatus(t("status_check"), "error");
      return;
    }
    saveDraft();
    send(collect());
  });

  form.addEventListener("input", function (event) {
    var key = keyOf(event.target);
    if (key === "phone") {
      checkPhone();
    } else if (key === "email") {
      checkEmail();
    } else if (key) {
      setHint(key, "");
    }
    event.target.classList.remove("is-invalid");
    saveDraft();
  });

  form.addEventListener("change", function (event) {
    if (keyOf(event.target) === "consent") {
      setHint("consent", "");
    }
    saveDraft();
  });

  var phoneInput = byKey("phone");
  if (phoneInput) {
    phoneInput.addEventListener("blur", function () {
      var formatted = formatPhone(phoneInput.value);
      if (formatted !== phoneInput.value) {
        phoneInput.value = formatted;
        saveDraft();
      }
    });
  }

  againBtn.addEventListener("click", resetToBlank);

  restoreDraft();
})();
