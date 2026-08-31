const assert = require("assert");
const voices = require("../../app/static/practice.js");

const sample = [
  { name: "Google US English", lang: "en-US", voiceURI: "en-us", localService: false },
  { name: "Kyoko", lang: "ja-JP", voiceURI: "kyoko", localService: true },
  { name: "Android JA", lang: "ja_JP", voiceURI: "ja_jp", localService: true },
  { name: "Google 日本語", lang: "ja-JP", voiceURI: "google-ja", localService: false },
  { name: "Nanami", lang: "ja-JP", voiceURI: "nanami", localService: false },
];

function testFilterAcceptsHyphenAndUnderscore() {
  const ja = voices.filterByLang(sample, "ja");
  assert.deepStrictEqual(
    ja.map((voice) => voice.name),
    ["Kyoko", "Android JA", "Google 日本語", "Nanami"],
  );
}

function testSortPrefersExactLocaleThenLocalService() {
  const sorted = voices.sortVoices(voices.filterByLang(sample, "ja-JP"), "ja-JP");
  assert.strictEqual(sorted[0].name, "Kyoko");
  assert.strictEqual(sorted[0].localService, true);
}

function testPickVoiceFallsBackFromUriToNameLangToLang() {
  const ja = voices.filterByLang(sample, "ja");
  const byUri = voices.pickVoice(ja, { voiceURI: "nanami", name: "x", lang: "x" }, "ja-JP");
  assert.strictEqual(byUri.name, "Nanami");
  const byNameLang = voices.pickVoice(
    ja,
    { voiceURI: "missing", name: "Google 日本語", lang: "ja-JP" },
    "ja-JP",
  );
  assert.strictEqual(byNameLang.name, "Google 日本語");
  const byLang = voices.pickVoice(
    ja,
    { voiceURI: "missing", name: "gone", lang: "ja_JP" },
    "ja-JP",
  );
  assert.strictEqual(byLang.name, "Android JA");
  const first = voices.pickVoice(ja, null, "ja-JP");
  assert.strictEqual(first.name, "Kyoko");
}

function testStorageRoundTrip() {
  const store = {
    data: {},
    getItem(key) { return this.data[key] || null; },
    setItem(key, value) { this.data[key] = value; }
  };
  voices.writeStoredVoice(store, "ja", { voiceURI: "kyoko", name: "Kyoko", lang: "ja-JP" });
  assert.strictEqual(store.getItem("rememate.practice.voice.ja").includes("Kyoko"), true);
  const stored = voices.readStoredVoice(store, "ja-JP");
  assert.deepStrictEqual(stored, { voiceURI: "kyoko", name: "Kyoko", lang: "ja-JP" });
}

testFilterAcceptsHyphenAndUnderscore();
testSortPrefersExactLocaleThenLocalService();
testPickVoiceFallsBackFromUriToNameLangToLang();
testStorageRoundTrip();

const chinese = [
  { name: "Google US English", lang: "en-US", voiceURI: "en-us", localService: false },
  { name: "Huihui", lang: "zh-CN", voiceURI: "huihui", localService: true },
  { name: "Android ZH", lang: "zh_CN", voiceURI: "zh_cn", localService: true },
  { name: "Android Hans", lang: "zh_CN_#Hans", voiceURI: "zh_hans", localService: true },
  { name: "Google 普通话", lang: "zh-CN", voiceURI: "google-zh", localService: false },
  { name: "Yating", lang: "zh-TW", voiceURI: "yating", localService: true },
  { name: "Kyoko", lang: "ja-JP", voiceURI: "kyoko", localService: true },
];

function testChineseFilterAcceptsHyphenUnderscoreAndBarePrefix() {
  const zhFromLocale = voices.filterByLang(chinese, "zh-CN");
  const zhFromUnderscore = voices.filterByLang(chinese, "zh_CN");
  const zhFromPrefix = voices.filterByLang(chinese, "zh");
  const names = ["Huihui", "Android ZH", "Android Hans", "Google 普通话", "Yating"];
  assert.deepStrictEqual(zhFromLocale.map((voice) => voice.name), names);
  assert.deepStrictEqual(zhFromUnderscore.map((voice) => voice.name), names);
  assert.deepStrictEqual(zhFromPrefix.map((voice) => voice.name), names);
}

function testChineseSortPrefersExactZhCNThenLocalService() {
  const sorted = voices.sortVoices(voices.filterByLang(chinese, "zh"), "zh-CN");
  assert.strictEqual(sorted[0].name, "Huihui");
  assert.strictEqual(sorted[0].lang, "zh-CN");
  assert.strictEqual(sorted[0].localService, true);
  assert.ok(sorted.findIndex((voice) => voice.lang === "zh-CN") <
    sorted.findIndex((voice) => voice.lang === "zh-TW"));
}

function testChinesePickVoiceFallsBackFromUriToNameLangToLang() {
  const zh = voices.filterByLang(chinese, "zh");
  const byUri = voices.pickVoice(zh, { voiceURI: "google-zh", name: "x", lang: "x" }, "zh-CN");
  assert.strictEqual(byUri.name, "Google 普通话");
  const byNameLang = voices.pickVoice(
    zh,
    { voiceURI: "missing", name: "Yating", lang: "zh-TW" },
    "zh-CN",
  );
  assert.strictEqual(byNameLang.name, "Yating");
  const byLang = voices.pickVoice(
    zh,
    { voiceURI: "missing", name: "gone", lang: "zh_CN" },
    "zh-CN",
  );
  assert.strictEqual(byLang.name, "Android ZH");
  const first = voices.pickVoice(zh, null, "zh-CN");
  assert.strictEqual(first.name, "Huihui");
}

function testChineseStorageRoundTrip() {
  const store = {
    data: {},
    getItem(key) { return this.data[key] || null; },
    setItem(key, value) { this.data[key] = value; }
  };
  voices.writeStoredVoice(store, "zh", { voiceURI: "huihui", name: "Huihui", lang: "zh-CN" });
  assert.strictEqual(store.getItem("rememate.practice.voice.zh").includes("Huihui"), true);
  const stored = voices.readStoredVoice(store, "zh-CN");
  assert.deepStrictEqual(stored, { voiceURI: "huihui", name: "Huihui", lang: "zh-CN" });
}

testChineseFilterAcceptsHyphenUnderscoreAndBarePrefix();
testChineseSortPrefersExactZhCNThenLocalService();
testChinesePickVoiceFallsBackFromUriToNameLangToLang();
testChineseStorageRoundTrip();

function testLanguageSwitchFormsMarkIntentionalNavigation() {
  var marked = false;
  var bound = [];
  var uiForm = {
    addEventListener: function (type, fn) {
      bound.push({ form: "ui", type: type, fn: fn });
    },
  };
  var langForm = {
    addEventListener: function (type, fn) {
      bound.push({ form: "lang", type: type, fn: fn });
    },
  };
  var documentRef = {
    querySelectorAll: function (selector) {
      assert.ok(selector.indexOf("ui-locale-form") !== -1);
      assert.ok(selector.indexOf("langSwitchForm") !== -1);
      return [uiForm, langForm];
    },
  };
  voices.bindIntentionalNavigation(documentRef, function () {
    marked = true;
  });
  assert.strictEqual(bound.length, 2);
  assert.strictEqual(bound[0].type, "submit");
  assert.strictEqual(bound[1].type, "submit");
  bound[0].fn();
  assert.strictEqual(marked, true);
}

testLanguageSwitchFormsMarkIntentionalNavigation();
console.log("ok");
