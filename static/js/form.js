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

  /* Мягкое форматирование: ничего не запрещаем, только приводим российский номер к виду.
     Любой другой формат (например, +375…) остаётся как ввёл посетитель. */
  function formatPhone(value) {
    var raw = String(value || "").trim();
    var digits = digitsOnly(raw);
    if (digits.length === 10) {
      digits = "7" + digits;
    }
    if (digits.length !== 11) {
      return raw;
    }
    if (digits.charAt(0) === "8") {
      digits = "7" + digits.slice(1);
    }
    if (digits.charAt(0) !== "7") {
      return raw;
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
      setHint("phone", email && email.value.trim() ? "" : "телефон или email — хотя бы одно из двух", "info");
      return;
    }
    if (/[^\d\s()+.\-]/.test(raw)) {
      setHint("phone", "в номере есть посторонние символы", "error");
      return;
    }
    var count = digitsOf(raw);
    if (count < PHONE_DIGITS_MIN) {
      setHint("phone", "цифр: " + count + " — нужно минимум " + PHONE_DIGITS_MIN, "info");
    } else if (count > PHONE_DIGITS_MAX) {
      setHint("phone", "цифр: " + count + " — больше " + PHONE_DIGITS_MAX + " не берём", "error");
    } else {
      setHint("phone", "цифр: " + count + " — этого достаточно", "ok");
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
      setHint("email", phone && phone.value.trim() ? "" : "email или телефон — хотя бы одно из двух", "info");
      return;
    }
    if (EMAIL_RE.test(raw)) {
      setHint("email", "адрес похож на настоящий", "ok");
    } else {
      setHint("email", "похоже, что адрес почты заполнен не полностью", "error");
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
      setHint("name", "введите имя — как к вам обращаться", "error");
      firstBad = firstBad || name;
    } else {
      setHint("name", "");
    }

    if (!phoneFilled && !emailFilled) {
      setHint("phone", "оставьте телефон или email — хотя бы одно из двух", "error");
      firstBad = firstBad || phone;
    } else if (phoneFilled) {
      var count = digitsOf(phone.value);
      if (count < PHONE_DIGITS_MIN) {
        setHint("phone", "в телефоне слишком мало цифр: " + count, "error");
        firstBad = firstBad || phone;
      } else if (count > PHONE_DIGITS_MAX) {
        setHint("phone", "в телефоне слишком много цифр: " + count, "error");
        firstBad = firstBad || phone;
      } else {
        setHint("phone", "");
      }
    } else {
      setHint("phone", "");
    }

    if (emailFilled && !EMAIL_RE.test(email.value.trim())) {
      setHint("email", "похоже, что адрес почты заполнен не полностью", "error");
      firstBad = firstBad || email;
    } else {
      setHint("email", "");
    }

    if (!consent.checked) {
      setHint("consent", "нужно согласие на обработку персональных данных", "error");
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
    setStatus("Черновик восстановлен — проверьте и отправьте.", "ok");
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
    doneNext.textContent = "Новая анкета через " + left + " с";
    stopResetTimer();
    resetTimer = window.setInterval(function () {
      left -= 1;
      if (left > 0) {
        doneNext.textContent = "Новая анкета через " + left + " с";
        return;
      }
      resetToBlank();
    }, 1000);
  }

  /* Разбирает 422: подсказки ставим под конкретные поля, в статус — первое сообщение. */
  function applyServerProblems(detail) {
    if (!Array.isArray(detail) || !detail.length) {
      return "Что-то пошло не так. Проверьте заполнение и отправьте ещё раз.";
    }
    var summary = "";
    detail.forEach(function (item) {
      /* Pydantic добавляет служебное "Value error, " — убираем его */
      var message = String(item.msg || "").replace(/^Value error,\s*/, "") || "проверьте заполнение полей";
      var key = Array.isArray(item.loc) && item.loc.length > 1 ? String(item.loc[item.loc.length - 1]) : "";
      if (!key) {
        PROBLEM_FIELDS.forEach(function (pair) {
          if (!key && pair[0].test(message)) {
            key = pair[1];
          }
        });
      }
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
        setStatus(applyServerProblems(result.data.detail), "error");
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

    var bad = validate();
    if (bad) {
      bad.focus();
      setStatus("Проверьте подсказки под полями.", "error");
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
