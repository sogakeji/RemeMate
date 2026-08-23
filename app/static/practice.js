(function () {
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
  var intentionalNavigation = false;
  var voiceFailureReported = false;

  function message(name) {
    return root.getAttribute("data-practice-" + name) || "";
  }

  function frenchVoices() {
    if (!synth) return [];
    return synth.getVoices().filter(function (voice) {
      return /^fr([-_]|$)/i.test(voice.lang || "");
    });
  }

  function setStatus(message) {
    if (status) status.textContent = message;
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
    var voices = frenchVoices();
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

  if (answerForm && durationInput) {
    answerForm.addEventListener("submit", function () {
      intentionalNavigation = true;
      durationInput.value = Math.max(0, Date.now() - questionStartedAt);
    });
  }

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
      if (!voices.length) return;
      var utterance = new SpeechSynthesisUtterance(
        button.getAttribute("data-practice-sentence") || ""
      );
      utterance.lang = voices[0].lang || "fr-FR";
      utterance.voice = voices[0];
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
})();
