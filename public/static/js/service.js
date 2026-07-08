/**
 * ══════════════════════════════════════════════════
 * State & Core Business Logic (API Services)
 * ══════════════════════════════════════════════════
 */

let state = {
  config: { hymn_folder: "", template_file: "", hymn_slots: [] },
  genSlots: [],
  templateSlides: [],
  choirSelectMode: null,
  bibleMeta: { books: [], abbr_to_id: {} },
  scriptureVerses: [],
  scriptureRef: "",
  scriptureBookName: "",
  scriptureChapter: "",
  scriptureVerseStart: "",
  scriptureVerseEnd: "",
  extraVerses: [], // [{id, slide_index, ref, book_name, chapter, verse_start, verse_end, verses:[]}]
};

let hymnSearchTimers = {};
let previewTimer = null;

// 애플리케이션 초기 데이터 바인딩
async function init() {
  try {
    const res = await fetch("/api/config");
    state.config = await res.json();

    if (state.config.hymn_folder)
      document.getElementById("cfg-hymn-folder").value =
        state.config.hymn_folder;

    if (state.config.template_file) {
      document.getElementById("cfg-template").value =
        state.config.template_file;
      document.getElementById("gen-template").value =
        state.config.template_file;
    }

    if (state.config.hymn_slots?.length > 0) {
      state.genSlots = state.config.hymn_slots.map((s, i) => ({
        id: Date.now() + i,
        name: s.name,
        after_slide_index: s.after_slide_index,
        hymn_number: "",
        hymn_title: "",
        skip: false,
      }));
      renderCfgSlots();
    }
    renderSlots();

    // 성경 데이터 메타 정보 로드
    const bm = await fetch("/api/bible-meta");
    state.bibleMeta = await bm.json();
  } catch (e) {
    console.warn("초기 데이터 로드 실패 (Config / Bible-Meta)", e);
  }
}

// 성경 책이름 입력 시 자동완성 로직
function onScriptureBookInput(val, dropdownId, statusId) {
  const dd = document.getElementById(dropdownId);
  const status = document.getElementById(statusId);
  if (!val || val.length < 1) {
    dd.style.display = "none";
    status.textContent = "";
    return;
  }
  const books = state.bibleMeta.books || [];
  const matches = books
    .filter((b) => b.abbr.startsWith(val) || b.name.includes(val))
    .slice(0, 8);
  if (!matches.length) {
    dd.style.display = "none";
    status.textContent = "";
    return;
  }
  dd.innerHTML = "";
  matches.forEach((b) => {
    const item = document.createElement("div");
    item.style.cssText =
      "padding:8px 12px;cursor:pointer;font-size:13px;border-bottom:1px solid #2a2010;display:flex;gap:8px;";
    item.innerHTML = `<span style="color:var(--gold);font-weight:600;min-width:36px">${b.abbr}</span>
      <span style="color:var(--cream)">${b.name}</span>`;
    const inputId = dropdownId === "sc-book-dropdown" ? "sc-book" : "ev-book";
    item.onmousedown = (e) => {
      e.preventDefault();
      document.getElementById(inputId).value = b.abbr;
      status.textContent = "✓ " + b.name;
      status.style.color = "var(--green)";
      dd.style.display = "none";
    };
    dd.appendChild(item);
  });
  dd.style.display = "block";
}

// 기본 성경 구절 API 호출
async function fetchScripture() {
  const book = document.getElementById("sc-book").value.trim();
  const ch = document.getElementById("sc-chapter").value;
  const vsS = document.getElementById("sc-verse-start").value;
  const vsE = document.getElementById("sc-verse-end").value;
  const status = document.getElementById("sc-fetch-status");

  if (!book || !ch || !vsS || !vsE) {
    showAlertMessage(
      "sc-fetch-status",
      "❌ 책·장·절을 모두 입력하세요",
      "var(--red)"
    );
    return;
  }
  status.textContent = "불러오는 중...";
  status.style.color = "var(--text-light)";
  try {
    const res = await fetch("/api/bible", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        book_abbr: book,
        chapter: parseInt(ch),
        verse_start: parseInt(vsS),
        verse_end: parseInt(vsE),
      }),
    });
    const data = await res.json();
    if (data.error) {
      showAlertMessage("sc-fetch-status", "❌ " + data.error, "var(--red)");
      return;
    }
    state.scriptureVerses = data.verses;
    state.scriptureRef = data.ref;
    state.scriptureBookName = data.book_name;
    state.scriptureChapter = data.chapter;
    state.scriptureVerseStart = data.verse_start;
    state.scriptureVerseEnd = data.verse_end;
    showAlertMessage(
      "sc-fetch-status",
      `✓ ${data.verses.length}절 로드됨`,
      "var(--green)"
    );
    renderScripturePreview();
  } catch (e) {
    showAlertMessage("sc-fetch-status", "❌ " + e.message, "var(--red)");
  }
}

function renderScripturePreview() {
  const verses = state.scriptureVerses;
  if (!verses.length) return;
  document.getElementById("sc-preview").style.display = "block";
  document.getElementById("sc-ref-badge").textContent = state.scriptureRef;
  const slideEl = document.getElementById("sc-slide-preview");
  slideEl.innerHTML = "";
  for (let i = 0; i < verses.length; i += 2) {
    const chunk = verses.slice(i, i + 2);
    const card = document.createElement("div");
    card.className = "scripture-slide-card";
    const lines = chunk.map((v) => `${v.num} ${v.text}`).join("\n");
    card.innerHTML = `<div class="slide-label">슬라이드 ${
      Math.floor(i / 2) + 1
    }</div>
      <div class="slide-body">${lines.replace(/\n/g, "<br>")}</div>`;
    slideEl.appendChild(card);
  }
}

// 추가 성경 구절 로직
async function addExtraVerse() {
  const slideIdx = document.getElementById("ev-slide-idx").value;
  const book = document.getElementById("ev-book").value.trim();
  const ch = document.getElementById("ev-chapter").value;
  const vsS = document.getElementById("ev-verse-start").value;
  const vsE = document.getElementById("ev-verse-end").value;
  const status = document.getElementById("ev-add-status");

  if (!slideIdx || !book || !ch || !vsS || !vsE) {
    showAlertMessage(
      "ev-add-status",
      "❌ 슬라이드 번호·책·장·절을 모두 입력하세요",
      "var(--red)"
    );
    return;
  }
  status.textContent = "불러오는 중...";
  status.style.color = "var(--text-light)";
  try {
    const res = await fetch("/api/bible", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        book_abbr: book,
        chapter: parseInt(ch),
        verse_start: parseInt(vsS),
        verse_end: parseInt(vsE),
      }),
    });
    const data = await res.json();
    if (data.error) {
      showAlertMessage("ev-add-status", "❌ " + data.error, "var(--red)");
      return;
    }

    state.extraVerses.push({
      id: Date.now(),
      slide_index: parseInt(slideIdx) - 1,
      ref: data.ref,
      book_name: data.book_name,
      verses: data.verses,
      chapter: data.chapter,
    });
    showAlertMessage("ev-add-status", `✓ ${data.ref} 추가됨`, "var(--green)");

    [
      "ev-slide-idx",
      "ev-book",
      "ev-chapter",
      "ev-verse-start",
      "ev-verse-end",
    ].forEach((id) => {
      document.getElementById(id).value = "";
    });
    document.getElementById("ev-book-status").textContent = "";
    renderExtraVerseList();
  } catch (e) {
    showAlertMessage("ev-add-status", "❌ " + e.message, "var(--red)");
  }
}

function renderExtraVerseList() {
  const listEl = document.getElementById("ev-list");
  listEl.innerHTML = "";
  if (!state.extraVerses.length) return;
  state.extraVerses.forEach((ev, idx) => {
    const div = document.createElement("div");
    div.className = "ev-item";
    div.innerHTML = `
      <div class="ev-item-info">
        <div class="ev-item-ref">${ev.ref}</div>
        <div class="ev-item-slide">슬라이드 ${ev.slide_index + 1} · ${
      ev.verses.length
    }절 · ${Math.ceil(ev.verses.length / 2)}장 분할</div>
      </div>
      <button class="btn btn-danger" onclick="removeExtraVerse(${idx})">✕</button>
    `;
    listEl.appendChild(div);
  });
}

function removeExtraVerse(idx) {
  state.extraVerses.splice(idx, 1);
  renderExtraVerseList();
}

// PPT 템플릿 정보 호출
async function loadTemplateSlides() {
  const path = document.getElementById("gen-template").value.trim();
  if (!path) return;

  const status = document.getElementById("gen-template-status");
  status.textContent = "불러오는 중...";
  status.style.color = "var(--text-light)";

  const res = await fetch("/api/template-info", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ template_file: path }),
  });
  const data = await res.json();

  if (data.error) {
    showAlertMessage("gen-template-status", "❌ " + data.error, "var(--red)");
    return;
  }

  state.templateSlides = data.slides;
  showAlertMessage(
    "gen-template-status",
    `✓ 슬라이드 ${data.total}장 로드됨`,
    "var(--green)"
  );

  const listEl = document.getElementById("gen-slides-list");
  listEl.innerHTML = "";
  data.slides.forEach((slide) => {
    const div = document.createElement("div");
    div.className = "slide-option";
    div.dataset.idx = slide.index;
    div.innerHTML = `<span class="slide-num">${slide.number}</span><span class="slide-text">${slide.preview_text}</span>`;
    div.onclick = () =>
      onSlideClick(slide.index, slide.number, slide.preview_text);
    listEl.appendChild(div);
  });

  document.getElementById("gen-slide-picker").style.display = "block";
  document.getElementById("gen-select-hint").textContent =
    "성가대 제목 슬라이드를 클릭하세요";
  state.choirSelectMode = "title";
}

function onSlideClick(idx, number, text) {
  const hint = document.getElementById("gen-select-hint");

  if (state.choirSelectMode === "title") {
    document.getElementById("choir-title-idx").value = number;
    const titleStatus = document.getElementById("choir-title-status");
    titleStatus.textContent = "✓ " + text.substring(0, 30);
    titleStatus.style.color = "var(--green)";
    state.choirSelectMode = "lyrics";
    hint.textContent = "이제 가사 템플릿 슬라이드를 클릭하세요";
    document
      .querySelectorAll("#gen-slides-list .slide-option")
      .forEach((el) => {
        el.classList.toggle("selected", parseInt(el.dataset.idx) === idx);
      });
  } else if (state.choirSelectMode === "lyrics") {
    document.getElementById("choir-lyrics-idx").value = number;
    const lyricsStatus = document.getElementById("choir-lyrics-status");
    lyricsStatus.textContent = "✓ " + text.substring(0, 30);
    lyricsStatus.style.color = "var(--green)";
    state.choirSelectMode = null;
    hint.textContent = "선택 완료! 가사를 입력하고 생성하세요.";
    document
      .querySelectorAll("#gen-slides-list .slide-option")
      .forEach((el) => {
        if (parseInt(el.dataset.idx) === idx) el.classList.add("selected");
      });
  }
}

// 생성 탭 찬송가 슬롯 관리
function renderSlots() {
  const list = document.getElementById("slot-list");
  list.innerHTML = "";

  if (state.genSlots.length === 0) {
    list.innerHTML =
      '<p style="color:var(--text-light);font-size:13px;text-align:center;padding:16px">+ 아래에서 슬롯을 추가하세요</p>';
    return;
  }

  state.genSlots.forEach((slot, idx) => {
    const div = document.createElement("div");
    div.className = "slot-item" + (slot.skip ? " skipped" : "");
    div.innerHTML = `
      <div class="slot-label">${slot.name}</div>
      <div class="after-slide">슬라이드 ${slot.after_slide_index + 1} 이후</div>
      <div class="slot-hymn-search">
        <input type="number" placeholder="번호" value="${
          slot.hymn_number || ""
        }"
          oninput="onHymnNumberInput(${idx}, this.value)" ${
      slot.skip ? "disabled" : ""
    } min="1" max="999">
        <div class="hymn-title-display ${
          slot.hymn_title === "없음"
            ? "not-found"
            : slot.hymn_title
            ? "found"
            : ""
        }">
          ${slot.hymn_title || ""}
        </div>
        <label style="cursor:pointer;margin:0;" title="파일 직접 업로드">
          <input type="file" accept=".ppt,.pptx,application/vnd.ms-powerpoint,application/vnd.openxmlformats-officedocument.presentationml.presentation" style="display:none"
            onchange="uploadHymnFile(${idx}, this)" ${
      slot.skip ? "disabled" : ""
    }>
          <span class="btn btn-outline btn-sm" style="white-space:nowrap">📎 파일</span>
        </label>
      </div>
      <label class="skip-toggle">
        <input type="checkbox" ${
          slot.skip ? "checked" : ""
        } onchange="toggleSkip(${idx})"> 스킵
      </label>
      <button class="btn btn-danger" onclick="removeSlot(${idx})">✕</button>
    `;
    list.appendChild(div);
  });
}

async function uploadHymnFile(idx, input) {
  const file = input.files[0];
  if (!file) return;
  const formData = new FormData();
  formData.append("file", file);
  try {
    const res = await fetch("/api/upload-hymn", {
      method: "POST",
      body: formData,
    });
    const data = await res.json();
    if (data.error) {
      alert("업로드 실패: " + data.error);
      return;
    }
    state.genSlots[idx].upload_path = data.upload_path;
    state.genSlots[idx].hymn_number = "";
    state.genSlots[idx].hymn_title = "📎 " + data.display_name;
    renderSlots();
  } catch (e) {
    alert("업로드 오류: " + e.message);
  }
}

async function onHymnNumberInput(idx, value) {
  state.genSlots[idx].hymn_number = value;
  state.genSlots[idx].hymn_title = "";
  state.genSlots[idx].upload_path = null;
  clearTimeout(hymnSearchTimers[idx]);
  if (!value) {
    renderSlots();
    return;
  }
  hymnSearchTimers[idx] = setTimeout(async () => {
    const hymnFolder = state.config.hymn_folder;
    if (!hymnFolder) {
      state.genSlots[idx].hymn_title = "설정에서 찬송가 폴더를 지정하세요";
      renderSlots();
      return;
    }
    const res = await fetch("/api/search-hymn", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ folder: hymnFolder, number: parseInt(value) }),
    });
    const data = await res.json();
    state.genSlots[idx].hymn_title = data.found ? data.title : "없음";
    renderSlots();
  }, 400);
}

function toggleSkip(idx) {
  state.genSlots[idx].skip = !state.genSlots[idx].skip;
  renderSlots();
}
function removeSlot(idx) {
  state.genSlots.splice(idx, 1);
  renderSlots();
}
function addSlot() {
  const name = document.getElementById("new-slot-name").value.trim();
  const after = document.getElementById("new-slot-after").value;
  if (!name || !after) {
    alert("이름과 슬라이드 번호를 입력해주세요");
    return;
  }
  state.genSlots.push({
    id: Date.now(),
    name,
    after_slide_index: parseInt(after) - 1,
    hymn_number: "",
    hymn_title: "",
    skip: false,
  });
  document.getElementById("new-slot-name").value = "";
  document.getElementById("new-slot-after").value = "";
  renderSlots();
}

// 성가대 가사 실시간 미리보기 연산
function autoPreviewChoir() {
  clearTimeout(previewTimer);
  previewTimer = setTimeout(() => {
    const text = document.getElementById("choir-lyrics").value.trim();
    const previewDiv = document.getElementById("choir-preview");
    const listEl = document.getElementById("choir-preview-list");

    if (!text) {
      previewDiv.style.display = "none";
      return;
    }

    const paragraphs = text
      .split(/\n\s*\n/)
      .map((p) => p.trim())
      .filter((p) => p);
    listEl.innerHTML = "";
    paragraphs.forEach((para, i) => {
      const div = document.createElement("div");
      div.className = "preview-slide-card";
      div.innerHTML = `<div class="slide-no">슬라이드 ${
        i + 1
      }</div><div class="slide-content">${para}</div>`;
      listEl.appendChild(div);
    });
    previewDiv.style.display = "block";
    listEl.style.display = "none";
    document.getElementById("choir-preview-close").style.display = "none";
  }, 300);
}

// 통합 고기능 PPT 생성 요청 처리
async function generatePPT() {
  const templateFile = document.getElementById("gen-template").value.trim();
  if (!templateFile) {
    showAlert("generate-alert", "템플릿 파일 경로를 입력해주세요", "error");
    return;
  }

  const choirEnabled = document.getElementById("choir-enabled").checked;
  const lyricsIdx = document.getElementById("choir-lyrics-idx").value;
  const lyrics = document.getElementById("choir-lyrics").value.trim();
  const titleIdx = document.getElementById("choir-title-idx").value;
  if (choirEnabled) {
    if (!lyricsIdx) {
      showAlert(
        "generate-alert",
        "성가대 가사 슬라이드 번호를 입력해주세요",
        "error"
      );
      return;
    }
    if (!lyrics) {
      showAlert("generate-alert", "성가대 가사를 입력해주세요", "error");
      return;
    }
  }

  const scriptureEnabled = document.getElementById("scripture-enabled").checked;
  const scTitleIdx = document.getElementById("sc-title-idx").value;
  const scLyricsIdx = document.getElementById("sc-lyrics-idx").value;
  if (scriptureEnabled) {
    if (!scLyricsIdx) {
      showAlert(
        "generate-alert",
        "성경 구절 템플릿 슬라이드 번호를 입력해주세요",
        "error"
      );
      return;
    }
    if (!state.scriptureVerses.length) {
      showAlert(
        "generate-alert",
        "성경 구절을 먼저 가져오세요 (📖 구절 가져오기)",
        "error"
      );
      return;
    }
  }

  document.getElementById("gen-loading").style.display = "block";
  document.getElementById("generate-alert").innerHTML = "";

  try {
    const payload = {
      template_file: templateFile,
      hymn_folder: state.config.hymn_folder,
      hymn_slots: state.genSlots.map((s) => ({
        name: s.name,
        after_slide_index: s.after_slide_index,
        hymn_number: s.hymn_number,
        upload_path: s.upload_path || null,
        skip: s.skip,
      })),
      choir: choirEnabled
        ? {
            title_slide_index: titleIdx ? parseInt(titleIdx) - 1 : null,
            lyrics_slide_index: lyricsIdx ? parseInt(lyricsIdx) - 1 : null,
            song_title: document
              .getElementById("choir-song-title")
              .value.trim(),
            lyrics,
            skip: false,
          }
        : null,
      scripture: scriptureEnabled
        ? {
            title_slide_index: scTitleIdx ? parseInt(scTitleIdx) - 1 : null,
            lyrics_slide_index: scLyricsIdx ? parseInt(scLyricsIdx) - 1 : null,
            verses: state.scriptureVerses,
            ref: state.scriptureRef,
            book_name: state.scriptureBookName,
            chapter: state.scriptureChapter,
            verse_start: state.scriptureVerseStart,
            verse_end: state.scriptureVerseEnd,
            skip: false,
          }
        : null,
      extra_verses: state.extraVerses.map((ev) => ({
        slide_index: ev.slide_index,
        book_name: ev.book_name,
        chapter: ev.chapter,
        verses: ev.verses,
      })),
    };

    const res = await fetch("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (res.headers.get("content-type")?.includes("json")) {
      const err = await res.json();
      showAlert("generate-alert", "❌ " + err.error, "error");
      return;
    }

    const blob = await res.blob();
    const cd = res.headers.get("Content-Disposition") || "";
    const m = cd.match(/filename[^;=\n]*=['"]?([^'"\n]+)['"]?/);
    const filename = m ? m[1] : "generated_presentation.pptx";

    downloadBlob(blob, filename);
    showAlert("generate-alert", "✓ PPT가 생성되었어요!", "success");
  } catch (e) {
    showAlert("generate-alert", "❌ 오류: " + e.message, "error");
  } finally {
    document.getElementById("gen-loading").style.display = "none";
  }
}

// 설정(Config) 탭 찬송가 슬롯 관리
function renderCfgSlots() {
  const list = document.getElementById("cfg-slot-list");
  list.innerHTML = "";
  let cfgSlots = state.config.hymn_slots || [];
  cfgSlots.forEach((slot, idx) => {
    const div = document.createElement("div");
    div.style.cssText =
      "display:flex;gap:10px;align-items:center;background:var(--dark3);border:1px solid #4a4020;border-radius:8px;padding:10px 14px;";
    div.innerHTML = `
      <span style="color:var(--gold);font-weight:600;font-size:13px;flex:1">${
        slot.name
      }</span>
      <span style="color:var(--text-light);font-size:12px">슬라이드 ${
        slot.after_slide_index + 1
      } 이후</span>
      <button class="btn btn-danger" onclick="removeCfgSlot(${idx})">✕</button>
    `;
    list.appendChild(div);
  });
  if (state.genSlots.length === 0 && cfgSlots.length > 0) {
    state.genSlots = cfgSlots.map((s, i) => ({
      id: Date.now() + i,
      name: s.name,
      after_slide_index: s.after_slide_index,
      hymn_number: "",
      hymn_title: "",
      upload_path: null,
      skip: false,
    }));
    renderSlots();
  }
}

function addCfgSlot() {
  const name = document.getElementById("cfg-new-slot-name").value.trim();
  const after = document.getElementById("cfg-new-slot-after").value;
  if (!name || !after) {
    alert("이름과 슬라이드 번호를 입력해주세요");
    return;
  }
  if (!state.config.hymn_slots) state.config.hymn_slots = [];
  state.config.hymn_slots.push({
    name,
    after_slide_index: parseInt(after) - 1,
  });
  document.getElementById("cfg-new-slot-name").value = "";
  document.getElementById("cfg-new-slot-after").value = "";
  renderCfgSlots();
}

function removeCfgSlot(idx) {
  state.config.hymn_slots.splice(idx, 1);
  renderCfgSlots();
}

async function checkHymnFolder() {
  const folder = document.getElementById("cfg-hymn-folder").value.trim();
  const status = document.getElementById("cfg-hymn-status");
  const res = await fetch("/api/scan-hymns", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ folder }),
  });
  const data = await res.json();
  if (data.error) {
    showAlertMessage("cfg-hymn-status", "❌ " + data.error, "var(--red)");
  } else {
    showAlertMessage(
      "cfg-hymn-status",
      `✓ 찬송가 ${data.hymns.length}개 발견`,
      "var(--green)"
    );
    state.config.hymn_folder = folder;
  }
}

async function checkTemplate() {
  const file = document.getElementById("cfg-template").value.trim();
  const res = await fetch("/api/template-info", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ template_file: file }),
  });
  const data = await res.json();
  if (data.error) {
    showAlertMessage("cfg-template-status", "❌ " + data.error, "var(--red)");
  } else {
    showAlertMessage(
      "cfg-template-status",
      `✓ 슬라이드 ${data.total}장`,
      "var(--green)"
    );
    state.config.template_file = file;
  }
}

async function saveConfig() {
  state.config.hymn_folder = document
    .getElementById("cfg-hymn-folder")
    .value.trim();
  state.config.template_file = document
    .getElementById("cfg-template")
    .value.trim();

  await fetch("/api/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(state.config),
  });

  if (state.config.template_file)
    document.getElementById("gen-template").value = state.config.template_file;

  if (state.config.hymn_slots) {
    state.genSlots = state.config.hymn_slots.map((s, i) => ({
      id: Date.now() + i,
      name: s.name,
      after_slide_index: s.after_slide_index,
      hymn_number: "",
      hymn_title: "",
      upload_path: null,
      skip: false,
    }));
    renderSlots();
  }
  showAlert("cfg-alert", "✓ 설정이 저장되었어요!", "success");
}

// 공통 다운로드 헬퍼
function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// UI Alert 알림창 컴포넌트 헬퍼
function showAlert(id, msg, type) {
  const el = document.getElementById(id);
  if (!el) return;
  el.innerHTML = `<div class="alert alert-${type}">${msg}</div>`;
  setTimeout(() => {
    el.innerHTML = "";
  }, 5000);
}

// 텍스트 상태 한 줄 알림창 헬퍼
function showAlertMessage(elementId, text, color) {
  const element = document.getElementById(elementId);
  if (!element) return;
  element.textContent = text;
  element.style.color = color;
}
