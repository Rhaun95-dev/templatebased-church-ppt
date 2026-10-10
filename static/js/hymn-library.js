/** 브라우저에서 사용자가 고른 로컬 찬송가 폴더를 읽는다 (서버에 라이브러리 없음) */
const HYMN_FILE_RE = /^(\d+)(?:장)?[\s_-]*(.*?)\.pptx$/i;

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
  let folderName = "";
  let pptxCount = 0;

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

  // items: [{ name, get: () => Promise<File> }] — 파일 내용은 실제로 고른 곡만 읽는다
  function index(items) {
    byNumber = new Map();
    pptxCount = 0;
    for (const item of items) {
      if (/\.pptx$/i.test(item.name) && !item.name.startsWith("~$")) pptxCount++;
      const p = parseHymnFilename(item.name);
      if (p && p.number !== null && !byNumber.has(p.number)) byNumber.set(p.number, { getFile: item.get, title: p.title });
    }
  }

  async function readHandle(h) {
    const files = [];
    const walk = async (dir, depth) => {
      for await (const entry of dir.values()) {
        if (entry.kind === "file") files.push({ name: entry.name, get: () => entry.getFile() });
        else if (entry.kind === "directory" && depth < 3) await walk(entry, depth + 1);
      }
    };
    await walk(h, 0);
    folderName = h.name;
    index(files);
  }

  async function pickFolder(onPicked) {
    if (window.showDirectoryPicker) {
      const prev = handle || (await loadHandle());  // 이전에 고른 폴더에서 시작
      handle = await window.showDirectoryPicker({
        mode: "read",
        ...(prev ? { startIn: prev } : {}),
      });
      if (onPicked) onPicked();
      await readHandle(handle);
      saveHandle(handle);
      return byNumber.size;
    }
    return new Promise((resolve) => {  // webkitdirectory 폴백
      const input = document.createElement("input");
      input.type = "file";
      input.webkitdirectory = true;
      input.onchange = () => {
        if (onPicked) onPicked();
        const fs = [...input.files].map((f) => ({ name: f.name, get: async () => f }));
        folderName = input.files[0] && input.files[0].webkitRelativePath ? input.files[0].webkitRelativePath.split("/")[0] : "";
        index(fs);
        resolve(byNumber.size);
      };
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

  // 이미 권한이 허용된 경우에만 조용히 복원 (권한 팝업 없이 시도)
  async function restoreIfGranted() {
    try {
      const h = await loadHandle();
      if (!h || (await h.queryPermission({ mode: "read" })) !== "granted") return false;
      handle = h;
      await readHandle(h);
      return true;
    } catch (e) { return false; }
  }

  return {
    pickFolder, restore, restoreIfGranted,
    find: (n) => byNumber.get(Number(n)) || null,
    get count() { return byNumber.size; },
    get ready() { return byNumber.size > 0; },
    get folderName() { return folderName; },
    get pptxCount() { return pptxCount; },
  };
})();

if (typeof module !== "undefined") module.exports = { parseHymnFilename };
