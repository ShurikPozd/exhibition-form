/* Клиентская логика анкеты: сбор данных, проверки до отправки, черновик в localStorage
   и экран «Спасибо».

   Проверки здесь — только для удобства: всё равно всё проверяется на сервере
   (schemas.py → utils/validators.py), поэтому правила повторяют серверные, а не наоборот. */

(function () {
  "use strict";

  var ENDPOINT = "/api/submissions";
  var DRAFT_KEY = "exhibition-form-draft-v1";
  var CHECK_GROUPS = ["role", "stall", "directions", "interest"];
  var EMAIL_RE = /^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$/;
  var PHONE_DIGITS_MIN = 10;
  var PHONE_DIGITS_MAX = 15;

  var form = document.getElementById("lead-form");
  var done = document.getElementById("done");
  var doneId = document.getElementById("done-id");
  var againBtn = document.getElementById("again");
  var status = document.getElementById("status");
  var submitBtn = document.getElementById("submit-btn");

  function byKey(key) {
    return document.getElementById("f-" + key);
  }

  function digitsOf(value) {
    return (String(value || "").match(/\d/g) || []).length;
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

  function fail(node, message) {
    if (node) {
      node.classList.add("is-invalid");
      node.focus();
    }
    setStatus(message, "error");
    return null;
  }

  /* Возвращает текст ошибки или null, если всё заполнено верно. */
  function validate() {
    var name = byKey("name");
    var phone = byKey("phone");
    var email = byKey("email");
    var consent = byKey("consent");

    if (!name.value.trim()) {
      return fail(name, "Введите имя — как к вам обращаться.");
    }
    if (!phone.value.trim() && !email.value.trim()) {
      return fail(phone, "Оставьте телефон или email, чтобы мы могли вам ответить.");
    }
    if (phone.value.trim()) {
      var count = digitsOf(phone.value);
      if (count < PHONE_DIGITS_MIN || count > PHONE_DIGITS_MAX) {
        return fail(phone, "В телефоне слишком " + (count < PHONE_DIGITS_MIN ? "мало" : "много") + " цифр.");
      }
    }
    if (email.value.trim() && !EMAIL_RE.test(email.value.trim())) {
      return fail(email, "Похоже, что адрес почты заполнен не полностью.");
    }
    if (!consent.checked) {
      return fail(consent, "Нужно согласие на обработку персональных данных.");
    }
    return null;
  }

  /* Собирает FormData в объект: группы чекбоксов становятся массивами. */
  function collect() {
    var payload = {};
    var data = new FormData(form);

    ["name", "company", "role_other", "phone", "email", "after_show"].forEach(function (key) {
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

    ["name", "company", "role_other", "phone", "email", "after_show"].forEach(function (key) {
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
    setStatus("Черновик восстановлен — проверьте и отправьте.", "ok");
  }

  function clearDraft() {
    try {
      window.localStorage.removeItem(DRAFT_KEY);
    } catch (err) {
      /* см. saveDraft */
    }
  }

  function showDone(id) {
    form.hidden = true;
    doneId.textContent = String(id);
    done.hidden = false;
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  /* Разбирает ответ сервера: 422 отдаёт список полей с сообщениями. */
  function serverProblem(data) {
    var detail = data && data.detail;
    if (typeof detail === "string") {
      return detail;
    }
    if (Array.isArray(detail) && detail.length) {
      var first = detail[0];
      var message = first.msg || "проверьте заполнение полей";
      /* Pydantic добавляет служебное "Value error, " — убираем его */
      return message.replace(/^Value error,\s*/, "");
    }
    return "Что-то пошло не так. Попробуйте ещё раз.";
  }

  function markServerFields(detail) {
    if (!Array.isArray(detail)) {
      return;
    }
    detail.forEach(function (item) {
      var key = Array.isArray(item.loc) ? item.loc[item.loc.length - 1] : null;
      var node = key ? byKey(key) : null;
      if (node) {
        node.classList.add("is-invalid");
      }
    });
  }

  function send(payload) {
    submitBtn.disabled = true;
    setStatus("Отправляем…");

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
        markServerFields(result.data.detail);
        setStatus(serverProblem(result.data), "error");
        submitBtn.disabled = false;
      })
      .catch(function (err) {
        setStatus("Нет связи с сервером. Проверьте интернет и отправьте ещё раз.", "error");
        submitBtn.disabled = false;
      });
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    clearInvalid();

    if (validate() !== null) {
      return;
    }
    saveDraft();
    send(collect());
  });

  form.addEventListener("input", saveDraft);
  form.addEventListener("change", saveDraft);

  againBtn.addEventListener("click", function () {
    form.reset();
    clearInvalid();
    clearDraft();
    setStatus("");
    done.hidden = true;
    form.hidden = false;
  });

  restoreDraft();
})();
