/**
 * ══════════════════════════════════════════════════
 * UI Interactions & Event Brawling
 * ══════════════════════════════════════════════════
 */

// 탭 전환 핸들러
function switchTab(name, btn) {
  document
    .querySelectorAll(".tab-panel")
    .forEach((p) => p.classList.remove("active"));
  document
    .querySelectorAll(".tab-btn")
    .forEach((b) => b.classList.remove("active"));
  document.getElementById("tab-" + name).classList.add("active");
  btn.classList.add("active");
}

// 성가대 섹션 활성화/비활성화 토글
function toggleChoirSection() {
  const enabled = document.getElementById("choir-enabled").checked;
  document
    .getElementById("choir-section")
    .classList.toggle("disabled", !enabled);
}

// 성경 구절 섹션 활성화/비활성화 토글
function toggleScriptureSection() {
  const en = document.getElementById("scripture-enabled").checked;
  document
    .getElementById("scripture-section")
    .classList.toggle("disabled", !en);
}

// 성경 구절 자동완성 드롭다운 이외의 영역 클릭 시 닫기
document.addEventListener("click", (e) => {
  ["sc-book-dropdown", "ev-book-dropdown"].forEach((id) => {
    const dd = document.getElementById(id);
    if (
      dd &&
      !dd.contains(e.target) &&
      e.target.id !== id.replace("-dropdown", "")
    ) {
      dd.style.display = "none";
    }
  });
});

// 성가대 미리보기 레이아웃 토글
function toggleChoirPreview() {
  const list = document.getElementById("choir-preview-list");
  const closeBtn = document.getElementById("choir-preview-close");

  if (list.style.display === "none") {
    list.style.display = "flex";
    closeBtn.style.display = "block";
  } else {
    list.style.display = "none";
    closeBtn.style.display = "none";
  }
}

// 성경 미리보기 레이아웃 토글
function toggleScripturePreview() {
  const list = document.getElementById("sc-slide-preview");
  const close = document.getElementById("sc-preview-close");
  const tog = document.getElementById("sc-preview-toggle");
  const open = list.style.display === "none";
  list.style.display = open ? "flex" : "none";
  close.style.display = open ? "block" : "none";
  tog.textContent = open
    ? "▼ 슬라이드 분할 미리보기"
    : "▶ 슬라이드 분할 미리보기";
}

// 초기 로딩 진입점 호출
document.addEventListener("DOMContentLoaded", () => {
  init().then(renderCfgSlots);
});
