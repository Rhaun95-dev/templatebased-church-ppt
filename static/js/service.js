/**
 * ══════════════════════════════════════════════════
 * State & Core Business Logic (API Services)
 * ══════════════════════════════════════════════════
 */

// DOM 조회 단축 헬퍼 (app.js에서도 공용으로 사용)
const $ = (id) => document.getElementById(id);

// JSON POST 요청 공용 헬퍼
async function postJSON(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return res.json();
}

// 설정에 저장된 슬롯 정보로 '생성' 탭용 슬롯 객체 생성
function createGenSlot(s, i) {
  return {
    id: Date.now() + i,
    name: s.name,
    after_slide_index: s.after_slide_index,
    hymn_number: "",
    hymn_title: "",
    upload_path: null,
    skip: false,
  };
}

let state = {
  config: {
    hymn_folder: "",
    template_file: "",
    hymn_slots: [],
    slide_defaults: {
      choir_title_idx: null,
      choir_lyrics_idx: null,
      scripture_title_idx: null,
      scripture_lyrics_idx: null,
      extra_verse_slide_idx: null,
    },
  },
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
let bookDropdownState = {}; // keyed by dropdownId: { matches, activeIndex, statusId }

// 애플리케이션 초기 데이터 바인딩
async function init() {
  try {
    const res = await fetch("/api/config");
    state.config = await res.json();

    if (state.config.hymn_folder)
      $("cfg-hymn-folder").value = state.config.hymn_folder;

    if (state.config.template_file) {
      $("cfg-template").value = state.config.template_file;
      $("gen-template").value = state.config.template_file;
    }

    if (state.config.hymn_slots?.length > 0) {
      state.genSlots = state.config.hymn_slots.map(createGenSlot);
      renderCfgSlots();
    }
    renderSlots();

    // 캐싱된 슬라이드 번호 기본값 적용 (성가대/성경구절/추가구절)
    applySlideDefaults();

    // 성가대 가사 입력칸을 더 길게, 성경책 입력을 한국어 기본으로
    applyInputUxDefaults();

    // 성경책 자동완성 드롭다운 키보드 탐색(↑/↓/Enter) 연결
    setupBookInputKeyboardNav();

    // 성경 데이터 메타 정보 로드
    const bm = await fetch("/api/bible-meta");
    state.bibleMeta = await bm.json();
  } catch (e) {
    console.warn("초기 데이터 로드 실패 (Config / Bible-Meta)", e);
  }
}

// 설정에 캐싱된 슬라이드 번호 기본값을 관련 입력칸에 채워 넣기
function applySlideDefaults() {
  const sd = state.config.slide_defaults || {};
  const fillIfEmpty = (id, val) => {
    const el = $(id);
    if (el && !el.value && (val || val === 0)) el.value = val;
  };
  fillIfEmpty("choir-title-idx", sd.choir_title_idx);
  fillIfEmpty("choir-lyrics-idx", sd.choir_lyrics_idx);
  fillIfEmpty("sc-title-idx", sd.scripture_title_idx);
  fillIfEmpty("sc-lyrics-idx", sd.scripture_lyrics_idx);
  fillIfEmpty("ev-slide-idx", sd.extra_verse_slide_idx);
}

// 성가대 가사 textarea 높이 확장 및 성경책 입력 한국어 기본 설정
// (전용 CSS/HTML 파일이 없어 JS에서 처리 - 스타일시트가 있다면 그쪽에서
//  직접 처리하는 편이 더 깔끔합니다)
function applyInputUxDefaults() {
  const lyrics = $("choir-lyrics");
  if (lyrics) {
    lyrics.style.minHeight = "220px";
    if (!lyrics.rows || lyrics.rows < 10) lyrics.rows = 10;
  }
  ["sc-book", "ev-book"].forEach((id) => {
    const el = $(id);
    if (!el) return;
    el.setAttribute("lang", "ko");
    if (!el.placeholder) el.placeholder = "예: 창세기";
  });
  ["sc-verse-end", "ev-verse-end"].forEach((id) => {
    const el = $(id);
    if (!el) return;
    if (!el.placeholder) el.placeholder = "선택 (미입력시 시작절과 동일)";
  });
}

// 자동완성 드롭다운 닫기 공통 처리
function closeBookDropdown(dropdownId) {
  const dd = $(dropdownId);
  if (dd) dd.style.display = "none";
  bookDropdownState[dropdownId] = null;
}

// 성경 책이름 입력 시 자동완성 로직
function onScriptureBookInput(val, dropdownId, statusId) {
  const status = $(statusId);
  if (!val || val.length < 1) {
    closeBookDropdown(dropdownId);
    status.textContent = "";
    return;
  }
  const books = state.bibleMeta.books || [];
  const matches = books
    .filter((b) => b.abbr.startsWith(val) || b.name.includes(val))
    .slice(0, 8);
  if (!matches.length) {
    closeBookDropdown(dropdownId);
    status.textContent = "";
    return;
  }
  bookDropdownState[dropdownId] = { matches, activeIndex: -1, statusId };
  renderBookDropdown(dropdownId);
  $(dropdownId).style.display = "block";
}

// 자동완성 드롭다운 렌더링 (키보드 활성 항목 하이라이트 포함)
function renderBookDropdown(dropdownId) {
  const dd = $(dropdownId);
  const entry = bookDropdownState[dropdownId];
  if (!dd || !entry) return;
  dd.innerHTML = "";
  entry.matches.forEach((b, i) => {
    const active = i === entry.activeIndex;
    const item = document.createElement("div");
    item.dataset.idx = i;
    item.style.cssText =
      "padding:8px 12px;cursor:pointer;font-size:13px;border-bottom:1px solid #2a2010;display:flex;gap:8px;" +
      (active ? "background:rgba(212,175,55,0.18);" : "");
    item.innerHTML = `<span style="color:var(--gold);font-weight:600;min-width:36px">${b.abbr}</span>
      <span style="color:var(--cream)">${b.name}</span>`;
    item.onmousedown = (e) => {
      e.preventDefault();
      selectBook(dropdownId, i);
    };
    dd.appendChild(item);
  });
}

// 자동완성 항목 선택 공통 처리 (마우스 클릭 / 키보드 Enter 공용)
function selectBook(dropdownId, idx) {
  const entry = bookDropdownState[dropdownId];
  if (!entry || !entry.matches[idx]) return;
  const b = entry.matches[idx];
  const inputId = dropdownId.replace("-dropdown", "");
  const status = $(entry.statusId);
  const input = $(inputId);
  if (input) input.value = b.abbr;
  if (status) {
    status.textContent = "✓ " + b.name;
    status.style.color = "var(--green)";
  }
  closeBookDropdown(dropdownId);
}

// 성경책 입력칸에서 ↑/↓로 항목 이동, Enter로 선택, Esc로 닫기
function onBookInputKeydown(e, dropdownId) {
  const entry = bookDropdownState[dropdownId];
  const dd = $(dropdownId);
  if (!entry || !dd || dd.style.display === "none") return;
  if (e.key === "ArrowDown") {
    e.preventDefault();
    entry.activeIndex = Math.min(
      entry.activeIndex + 1,
      entry.matches.length - 1,
    );
    renderBookDropdown(dropdownId);
    scrollActiveBookIntoView(dropdownId);
  } else if (e.key === "ArrowUp") {
    e.preventDefault();
    entry.activeIndex = Math.max(entry.activeIndex - 1, 0);
    renderBookDropdown(dropdownId);
    scrollActiveBookIntoView(dropdownId);
  } else if (e.key === "Enter") {
    if (entry.activeIndex >= 0) {
      e.preventDefault();
      selectBook(dropdownId, entry.activeIndex);
    }
  } else if (e.key === "Escape") {
    closeBookDropdown(dropdownId);
  }
}

function scrollActiveBookIntoView(dropdownId) {
  const dd = $(dropdownId);
  const entry = bookDropdownState[dropdownId];
  if (!dd || !entry) return;
  const activeEl = dd.querySelector(`[data-idx="${entry.activeIndex}"]`);
  if (activeEl) activeEl.scrollIntoView({ block: "nearest" });
}

// 성경책 입력칸(sc-book, ev-book)에 키보드 탐색 리스너 연결
function setupBookInputKeyboardNav() {
  ["sc-book", "ev-book"].forEach((inputId) => {
    const el = $(inputId);
    if (!el) return;
    el.addEventListener("keydown", (e) =>
      onBookInputKeydown(e, inputId + "-dropdown"),
    );
  });
}

// 성경 구절 API 공용 호출 (기본 구절 / 추가 구절에서 공유)
function fetchBibleVerses(bookAbbr, chapter, verseStart, verseEnd) {
  return postJSON("/api/bible", {
    book_abbr: bookAbbr,
    chapter: parseInt(chapter),
    verse_start: parseInt(verseStart),
    verse_end: parseInt(verseEnd),
  });
}

// 기본 성경 구절 API 호출
async function fetchScripture() {
  const book = $("sc-book").value.trim();
  const ch = $("sc-chapter").value;
  const vsS = $("sc-verse-start").value;
  const vsEraw = $("sc-verse-end").value;
  const vsE = vsEraw || vsS; // 끝절 미입력 시 시작절과 동일(한 절)로 처리
  const status = $("sc-fetch-status");

  if (!book || !ch || !vsS) {
    showAlertMessage(
      "sc-fetch-status",
      "❌ 책·장·시작절을 입력하세요",
      "var(--red)",
    );
    return;
  }
  status.textContent = "불러오는 중...";
  status.style.color = "var(--text-light)";
  try {
    const data = await fetchBibleVerses(book, ch, vsS, vsE);
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
      "var(--green)",
    );
    renderScripturePreview();
  } catch (e) {
    showAlertMessage("sc-fetch-status", "❌ " + e.message, "var(--red)");
  }
}

function renderScripturePreview() {
  const verses = state.scriptureVerses;
  if (!verses.length) return;
  $("sc-preview").style.display = "block";
  $("sc-ref-badge").textContent = state.scriptureRef;
  const slideEl = $("sc-slide-preview");
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
  const slideIdx = $("ev-slide-idx").value;
  const book = $("ev-book").value.trim();
  const ch = $("ev-chapter").value;
  const vsS = $("ev-verse-start").value;
  const vsEraw = $("ev-verse-end").value;
  const vsE = vsEraw || vsS; // 끝절 미입력 시 시작절과 동일(한 절)로 처리
  const status = $("ev-add-status");

  if (!slideIdx || !book || !ch || !vsS) {
    showAlertMessage(
      "ev-add-status",
      "❌ 슬라이드 번호·책·장·시작절을 입력하세요",
      "var(--red)",
    );
    return;
  }
  status.textContent = "불러오는 중...";
  status.style.color = "var(--text-light)";
  try {
    const data = await fetchBibleVerses(book, ch, vsS, vsE);
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

    ["ev-book", "ev-chapter", "ev-verse-start", "ev-verse-end"].forEach(
      (id) => {
        $(id).value = "";
      },
    );
    // 슬라이드 번호는 비우지 않고 캐싱된 기본값으로 되돌림
    const defaultEvIdx = state.config.slide_defaults?.extra_verse_slide_idx;
    $("ev-slide-idx").value = defaultEvIdx || "";
    $("ev-book-status").textContent = "";
    renderExtraVerseList();
  } catch (e) {
    showAlertMessage("ev-add-status", "❌ " + e.message, "var(--red)");
  }
}

function renderExtraVerseList() {
  const listEl = $("ev-list");
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
  const path = $("gen-template").value.trim();
  if (!path) return;

  const status = $("gen-template-status");
  status.textContent = "불러오는 중...";
  status.style.color = "var(--text-light)";

  const data = await postJSON("/api/template-info", { template_file: path });

  if (data.error) {
    showAlertMessage("gen-template-status", "❌ " + data.error, "var(--red)");
    return;
  }

  state.templateSlides = data.slides;
  showAlertMessage(
    "gen-template-status",
    `✓ 슬라이드 ${data.total}장 로드됨`,
    "var(--green)",
  );

  const listEl = $("gen-slides-list");
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

  $("gen-slide-picker").style.display = "block";
  $("gen-select-hint").textContent = "성가대 제목 슬라이드를 클릭하세요";
  state.choirSelectMode = "title";
}

function onSlideClick(idx, number, text) {
  const hint = $("gen-select-hint");

  if (state.choirSelectMode === "title") {
    $("choir-title-idx").value = number;
    const titleStatus = $("choir-title-status");
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
    $("choir-lyrics-idx").value = number;
    const lyricsStatus = $("choir-lyrics-status");
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
  const list = $("slot-list");
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
    const data = await postJSON("/api/search-hymn", {
      folder: hymnFolder,
      number: parseInt(value),
    });
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
  const name = $("new-slot-name").value.trim();
  const after = $("new-slot-after").value;
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
  $("new-slot-name").value = "";
  $("new-slot-after").value = "";
  renderSlots();
}

// 성가대 가사 실시간 미리보기 연산
function autoPreviewChoir() {
  clearTimeout(previewTimer);
  previewTimer = setTimeout(() => {
    const text = $("choir-lyrics").value.trim();
    const previewDiv = $("choir-preview");
    const listEl = $("choir-preview-list");

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
    $("choir-preview-close").style.display = "none";
  }, 300);
}

// 통합 고기능 PPT 생성 요청 처리
async function generatePPT() {
  const templateFile = $("gen-template").value.trim();
  if (!templateFile) {
    showAlert("generate-alert", "템플릿 파일 경로를 입력해주세요", "error");
    return;
  }

  const choirEnabled = $("choir-enabled").checked;
  const lyricsIdx = $("choir-lyrics-idx").value;
  const lyrics = $("choir-lyrics").value.trim();
  const titleIdx = $("choir-title-idx").value;
  if (choirEnabled) {
    if (!lyricsIdx) {
      showAlert(
        "generate-alert",
        "성가대 가사 슬라이드 번호를 입력해주세요",
        "error",
      );
      return;
    }
    if (!lyrics) {
      showAlert("generate-alert", "성가대 가사를 입력해주세요", "error");
      return;
    }
  }

  const scriptureEnabled = $("scripture-enabled").checked;
  const scTitleIdx = $("sc-title-idx").value;
  const scLyricsIdx = $("sc-lyrics-idx").value;
  if (scriptureEnabled) {
    if (!scLyricsIdx) {
      showAlert(
        "generate-alert",
        "성경 구절 템플릿 슬라이드 번호를 입력해주세요",
        "error",
      );
      return;
    }
    if (!state.scriptureVerses.length) {
      showAlert(
        "generate-alert",
        "성경 구절을 먼저 가져오세요 (📖 구절 가져오기)",
        "error",
      );
      return;
    }
  }

  $("gen-loading").style.display = "block";
  $("generate-alert").innerHTML = "";

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
            song_title: $("choir-song-title").value.trim(),
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
    $("gen-loading").style.display = "none";
  }
}

// 설정(Config) 탭 찬송가 슬롯 관리
function renderCfgSlots() {
  const list = $("cfg-slot-list");
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
    state.genSlots = cfgSlots.map(createGenSlot);
    renderSlots();
  }
}

function addCfgSlot() {
  const name = $("cfg-new-slot-name").value.trim();
  const after = $("cfg-new-slot-after").value;
  if (!name || !after) {
    alert("이름과 슬라이드 번호를 입력해주세요");
    return;
  }
  if (!state.config.hymn_slots) state.config.hymn_slots = [];
  state.config.hymn_slots.push({
    name,
    after_slide_index: parseInt(after) - 1,
  });
  $("cfg-new-slot-name").value = "";
  $("cfg-new-slot-after").value = "";
  renderCfgSlots();
}

function removeCfgSlot(idx) {
  state.config.hymn_slots.splice(idx, 1);
  renderCfgSlots();
}

async function checkHymnFolder() {
  const folder = $("cfg-hymn-folder").value.trim();
  const data = await postJSON("/api/scan-hymns", { folder });
  if (data.error) {
    showAlertMessage("cfg-hymn-status", "❌ " + data.error, "var(--red)");
  } else {
    showAlertMessage(
      "cfg-hymn-status",
      `✓ 찬송가 ${data.hymns.length}개 발견`,
      "var(--green)",
    );
    state.config.hymn_folder = folder;
  }
}

async function checkTemplate() {
  const file = $("cfg-template").value.trim();
  const data = await postJSON("/api/template-info", { template_file: file });
  if (data.error) {
    showAlertMessage("cfg-template-status", "❌ " + data.error, "var(--red)");
  } else {
    showAlertMessage(
      "cfg-template-status",
      `✓ 슬라이드 ${data.total}장`,
      "var(--green)",
    );
    state.config.template_file = file;
  }
}

async function saveConfig() {
  state.config.hymn_folder = $("cfg-hymn-folder").value.trim();
  state.config.template_file = $("cfg-template").value.trim();

  // 성가대/성경구절/추가구절 슬라이드 번호 기본값 캐싱
  const readIdx = (id) => {
    const v = $(id)?.value;
    return v ? parseInt(v) : null;
  };
  state.config.slide_defaults = {
    choir_title_idx: readIdx("choir-title-idx"),
    choir_lyrics_idx: readIdx("choir-lyrics-idx"),
    scripture_title_idx: readIdx("sc-title-idx"),
    scripture_lyrics_idx: readIdx("sc-lyrics-idx"),
    extra_verse_slide_idx: readIdx("ev-slide-idx"),
  };

  await fetch("/api/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(state.config),
  });

  if (state.config.template_file)
    $("gen-template").value = state.config.template_file;

  if (state.config.hymn_slots) {
    state.genSlots = state.config.hymn_slots.map(createGenSlot);
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
  const el = $(id);
  if (!el) return;
  el.innerHTML = `<div class="alert alert-${type}">${msg}</div>`;
  setTimeout(() => {
    el.innerHTML = "";
  }, 5000);
}

// 텍스트 상태 한 줄 알림창 헬퍼
function showAlertMessage(elementId, text, color) {
  const element = $(elementId);
  if (!element) return;
  element.textContent = text;
  element.style.color = color;
}
