/** 사용자가 브라우저에서 고른 템플릿 파일 (서버에 저장하지 않고 PPT 생성 요청 때 함께 보낸다) */
const TemplateLibrary = (() => {
  const DB = "church-ppt", STORE = "handles", KEY = "template-file";
  const PPTX_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.presentation";
  let handle = null; // showOpenFilePicker 핸들 — 매번 디스크의 최신 파일을 읽는다
  let fallbackFile = null; // 파일 핸들을 지원하지 않는 브라우저용 (새로고침하면 사라짐)
  let name = "";

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

  async function pick() {
    if (window.showOpenFilePicker) {
      const prev = handle || (await loadHandle());
      const [h] = await window.showOpenFilePicker({
        multiple: false,
        types: [{ description: "PowerPoint 템플릿", accept: { [PPTX_TYPE]: [".pptx"] } }],
        ...(prev ? { startIn: prev } : {}),
      });
      handle = h;
      fallbackFile = null;
      name = h.name;
      saveHandle(h);
      return name;
    }
    return new Promise((resolve, reject) => {  // input[type=file] 폴백
      const input = document.createElement("input");
      input.type = "file";
      input.accept = ".pptx";
      input.onchange = () => {
        const f = input.files[0];
        if (!f) return reject(Object.assign(new Error("취소됨"), { name: "AbortError" }));
        handle = null;
        fallbackFile = f;
        name = f.name;
        resolve(name);
      };
      input.click();
    });
  }

  // 이전에 고른 파일 이름만 복원 (실제 읽기는 생성할 때 권한 확인 후)
  async function restore() {
    const h = await loadHandle();
    if (!h) return false;
    handle = h;
    name = h.name;
    return true;
  }

  // 생성 직전에 호출: 필요하면 권한을 다시 요청하고 최신 File을 돌려준다
  async function getFile() {
    if (handle) {
      if ((await handle.queryPermission({ mode: "read" })) !== "granted" &&
          (await handle.requestPermission({ mode: "read" })) !== "granted") {
        throw new Error("템플릿 파일 읽기 권한이 필요해요");
      }
      return await handle.getFile();
    }
    return fallbackFile;
  }

  return {
    pick, restore, getFile,
    get ready() { return !!(handle || fallbackFile); },
    get name() { return name; },
  };
})();
