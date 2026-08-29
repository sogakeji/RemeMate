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
console.log("ok");
