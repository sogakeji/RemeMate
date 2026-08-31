(function (global) {
  var voicesApi = {
    langPrefix: function (value) {
      return String(value || "").split(/[-_]/)[0].toLowerCase();
    },
    matchesLang: function (voiceLang, wanted) {
      var prefix = voicesApi.langPrefix(wanted);
      if (!prefix) return false;
      return new RegExp("^" + prefix + "([-_]|$)", "i").test(voiceLang || "");
    },
    filterByLang: function (voices, wanted) {
      return (voices || []).filter(function (voice) {
        return voicesApi.matchesLang(voice.lang, wanted);
      });
    },
    sortVoices: function (voices, wantedLocale) {
      var wanted = String(wantedLocale || "").toLowerCase();
      return (voices || []).slice().sort(function (left, right) {
        var leftLang = String(left.lang || "").toLowerCase();
        var rightLang = String(right.lang || "").toLowerCase();
        var leftExact = leftLang === wanted ? 0 : 1;
        var rightExact = rightLang === wanted ? 0 : 1;
        if (leftExact !== rightExact) return leftExact - rightExact;
        var leftLocal = left.localService ? 0 : 1;
        var rightLocal = right.localService ? 0 : 1;
        if (leftLocal !== rightLocal) return leftLocal - rightLocal;
        return String(left.name || "").localeCompare(String(right.name || ""));
      });
    },
    pickVoice: function (voices, stored, wanted) {
      var filtered = voicesApi.sortVoices(
        voicesApi.filterByLang(voices, wanted),
        wanted
      );
      if (!filtered.length) return null;
      if (stored) {
        var byUri = filtered.filter(function (voice) {
          return stored.voiceURI && voice.voiceURI === stored.voiceURI;
        })[0];
        if (byUri) return byUri;
        var byNameLang = filtered.filter(function (voice) {
          return voice.name === stored.name && (voice.lang || "") === (stored.lang || "");
        })[0];
        if (byNameLang) return byNameLang;
        var byLang = filtered.filter(function (voice) {
          return stored.lang && (voice.lang || "") === stored.lang;
        })[0];
        if (byLang) return byLang;
      }
      return filtered[0];
    },
    storageKey: function (wanted) {
      var prefix = voicesApi.langPrefix(wanted) || "default";
      return "rememate.practice.voice." + prefix;
    },
    readStoredVoice: function (storage, wanted) {
      if (!storage) return null;
      try {
        var raw = storage.getItem(voicesApi.storageKey(wanted));
        if (!raw) return null;
        var parsed = JSON.parse(raw);
        if (!parsed || typeof parsed !== "object") return null;
        return {
          voiceURI: parsed.voiceURI || "",
          name: parsed.name || "",
          lang: parsed.lang || ""
        };
      } catch (err) {
        return null;
      }
    },
    writeStoredVoice: function (storage, wanted, voice) {
      if (!storage || !voice) return;
      try {
        storage.setItem(voicesApi.storageKey(wanted), JSON.stringify({
          voiceURI: voice.voiceURI || "",
          name: voice.name || "",
          lang: voice.lang || ""
        }));
      } catch (err) {
        return;
      }
    },
    bindIntentionalNavigation: function (documentRef, mark) {
      if (!documentRef || typeof mark !== "function") return;
      if (typeof documentRef.querySelectorAll !== "function") return;
      var forms = documentRef.querySelectorAll(".ui-locale-form, #langSwitchForm");
      Array.prototype.forEach.call(forms, function (form) {
        if (form && form.addEventListener) {
          form.addEventListener("submit", mark);
        }
      });
    }
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = voicesApi;
  }

  if (typeof document === "undefined") return;

  var root = document.querySelector("[data-practice-root]");
  if (!root) return;

  var synth = window.speechSynthesis;
  var start = root.querySelector("[data-practice-start]");
  var retry = root.querySelector("[data-practice-retry]");
  var status = root.querySelector("[data-practice-voice-status]");
  var voiceInput = root.querySelector("[data-practice-voice-input]");
  var playButtons = root.querySelectorAll("[data-practice-play]");
  var answerForm = root.querySelector(".practice-form");
  var durationInput = root.querySelector("[data-practice-duration]");
  var questionStartedAt = Date.now();
  var abandoning = root.getAttribute("data-practice-abandon-url");
  var voiceReportUrl = root.getAttribute("data-practice-voice-report-url");
  var wantedLang = root.getAttribute("data-practice-voice-lang")
    || root.getAttribute("data-practice-voice-locale")
    || "fr";
  var wantedLocale = root.getAttribute("data-practice-voice-locale") || wantedLang;
  var intentionalNavigation = false;
  var voiceFailureReported = false;

  function message(name) {
    return root.getAttribute("data-practice-" + name) || "";
  }

  function matchingVoices() {
    if (!synth) return [];
    return voicesApi.filterByLang(synth.getVoices(), wantedLang);
  }

  function selectedVoice(voices) {
    var stored = voicesApi.readStoredVoice(window.localStorage, wantedLang);
    var picked = voicesApi.pickVoice(voices, stored, wantedLocale);
    if (picked) voicesApi.writeStoredVoice(window.localStorage, wantedLang, picked);
    return picked;
  }

  function setStatus(messageText) {
    if (status) status.textContent = messageText;
  }

  function reportVoiceUnavailable() {
    if (!voiceReportUrl || voiceFailureReported) return;
    voiceFailureReported = true;
    var csrf = root.querySelector('[name="csrf_token"]');
    if (!csrf) csrf = document.querySelector('meta[name="csrf-token"]');
    var payload = new FormData();
    if (csrf) payload.append("csrf_token", csrf.value || csrf.getAttribute("content"));
    fetch(voiceReportUrl, {
      method: "POST",
      body: payload,
      credentials: "same-origin",
      headers: csrf ? {"X-CSRFToken": csrf.value || csrf.getAttribute("content")} : {},
      keepalive: true
    }).catch(function () {
      voiceFailureReported = false;
    });
  }

  function updateVoiceState() {
    if (!synth) {
      setStatus(message("voice-unsupported"));
      reportVoiceUnavailable();
      if (start) start.disabled = true;
      if (voiceInput) voiceInput.value = "0";
      if (retry) retry.hidden = false;
      return [];
    }
    var voices = matchingVoices();
    if (!voices.length) {
      setStatus(message("voice-missing"));
      reportVoiceUnavailable();
      if (start) start.disabled = true;
      if (voiceInput) voiceInput.value = "0";
      if (playButtons.length) playButtons.forEach(function (button) {
        button.disabled = true;
      });
      if (retry) retry.hidden = false;
      return [];
    }
    setStatus(message("voice-ready"));
    if (start) start.disabled = false;
    if (voiceInput) voiceInput.value = "1";
    if (playButtons.length) playButtons.forEach(function (button) {
      button.disabled = false;
    });
    if (retry) retry.hidden = true;
    return voices;
  }

  function checkVoices() {
    setStatus(message("voice-checking"));
    if (!synth) {
      updateVoiceState();
      return;
    }
    if (synth.getVoices().length) {
      updateVoiceState();
      return;
    }
    var finished = false;
    function finish() {
      if (finished) return;
      finished = true;
      synth.removeEventListener("voiceschanged", finish);
      updateVoiceState();
    }
    synth.addEventListener("voiceschanged", finish);
    window.setTimeout(finish, 900);
  }

  if (retry) retry.addEventListener("click", checkVoices);
  if (synth) synth.addEventListener("voiceschanged", updateVoiceState);
  checkVoices();

  function markIntentionalNavigation() {
    intentionalNavigation = true;
  }

  if (answerForm && durationInput) {
    answerForm.addEventListener("submit", function () {
      markIntentionalNavigation();
      durationInput.value = Math.max(0, Date.now() - questionStartedAt);
    });
  }
  voicesApi.bindIntentionalNavigation(document, markIntentionalNavigation);

  if (abandoning && navigator.sendBeacon) {
    window.addEventListener("pagehide", function () {
      if (intentionalNavigation) return;
      var csrf = root.querySelector('[name="csrf_token"]');
      var payload = new FormData();
      if (csrf) payload.append("csrf_token", csrf.value);
      navigator.sendBeacon(abandoning, payload);
    });
  }

  playButtons.forEach(function (button) {
    button.addEventListener("click", function () {
      var voices = updateVoiceState();
      var voice = selectedVoice(voices);
      if (!voice) return;
      var utterance = new SpeechSynthesisUtterance(
        button.getAttribute("data-practice-sentence") || ""
      );
      utterance.lang = voice.lang || wantedLocale;
      utterance.voice = voice;
      var replayUrl = button.getAttribute("data-practice-replay-url");
      if (replayUrl) {
        var csrf = root.querySelector('[name="csrf_token"]');
        fetch(replayUrl, {
          method: "POST",
          headers: csrf ? {"X-CSRFToken": csrf.value} : {}
        });
      }
      synth.cancel();
      synth.speak(utterance);
    });
  });
})(typeof globalThis !== "undefined" ? globalThis : this);
