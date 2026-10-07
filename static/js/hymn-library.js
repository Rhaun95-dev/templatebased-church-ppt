/** 브라우저에서 사용자가 고른 로컬 찬송가 폴더를 읽는다 (서버에 라이브러리 없음) */
const HYMN_FILE_RE = /^(\d+)[\s_-]*(.*?)\.pptx$/i;

function parseHymnFilename(name) {
  if (name.startsWith("~$")) return null;
  if (!/\.pptx$/i.test(name)) return null;
  const m = HYMN_FILE_RE.exec(name);
  if (m) return { number: parseInt(m[1], 10), title: m[2].trim() };
  return { number: null, title: name.replace(/\.pptx$/i, "") };
}

const HymnLibrary = (() => {
  const DB = "church-ppt", STORE = "handles", KEY = "hymn-folder";
  let byNumber = new Map();
  let handle = null;

  const idb = () =>
    new Promise((resolve, reject) => {
      const req = indexedDB.open(DB, 1);
      req.onupgradeneeded = () => req.result.createObjectStore(STORE);
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  async function saveHandle(h) {
    try {
      const db = await idb();
      db.transaction(STORE, "readwrite").objectStore(STORE).put(h, KEY);
    } catch (e) { /* 기억하지 못해도 동작에는 영향 없음 */ }
  }
  async function loadHandle() {
    try {
      const db = await idb();
      return await new Promise((res) => {
        const r = db.transaction(STORE).objectStore(STORE).get(KEY);
        r.onsuccess = () => res(r.result || null);
        r.onerror = () => res(null);
      });
    } catch (e) { return null; }
  }

  function index(files) {
    byNumber = new Map();
    for (const file of files) {
      const p = parseHymnFilename(file.name);
      if (p && p.number !== null && !byNumber.has(p.number)) byNumber.set(p.number, { file, title: p.title });
    }
  }

  async function readHandle(h) {
    const files = [];
    for await (const entry of h.values()) {
      if (entry.kind === "file") files.push(await entry.getFile());
    }
    index(files);
  }

  async function pickFolder() {
    if (window.showDirectoryPicker) {
      handle = await window.showDirectoryPicker({ mode: "read" });
      await readHandle(handle);
      saveHandle(handle);
      return byNumber.size;
    }
    return new Promise((resolve) => {  // webkitdirectory 폴백
      const input = document.createElement("input");
      input.type = "file";
      input.webkitdirectory = true;
      input.onchange = () => { index([...input.files]); resolve(byNumber.size); };
      input.click();
    });
  }

  // 저장된 폴더 핸들 복원 (세션마다 권한 재요청 필요 → 사용자 클릭 안에서 호출)
  async function restore() {
    const h = handle || (await loadHandle());
    if (!h) return false;
    if ((await h.queryPermission({ mode: "read" })) !== "granted" &&
        (await h.requestPermission({ mode: "read" })) !== "granted") return false;
    handle = h;
    await readHandle(h);
    return true;
  }

  return {
    pickFolder, restore,
    find: (n) => byNumber.get(Number(n)) || null,
    get count() { return byNumber.size; },
    get ready() { return byNumber.size > 0; },
  };
})();

if (typeof module !== "undefined") module.exports = { parseHymnFilename };
