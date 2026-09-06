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
  $("tab-" + name).classList.add("active");
  btn.classList.add("active");
}

// 섹션 활성화 체크박스에 따라 대상 섹션의 disabled 표시 토글
function toggleSectionEnabled(checkboxId, sectionId) {
  const enabled = $(checkboxId).checked;
  $(sectionId).classList.toggle("disabled", !enabled);
}

// 성가대 섹션 활성화/비활성화 토글
function toggleChoirSection() {
  toggleSectionEnabled("choir-enabled", "choir-section");
}

// 성경 구절 섹션 활성화/비활성화 토글
function toggleScriptureSection() {
  toggleSectionEnabled("scripture-enabled", "scripture-section");
}

// 성경 구절 자동완성 드롭다운 이외의 영역 클릭 시 닫기
document.addEventListener("click", (e) => {
  ["sc-book-dropdown", "ev-book-dropdown"].forEach((id) => {
    const dd = $(id);
    if (
      dd &&
      !dd.contains(e.target) &&
      e.target.id !== id.replace("-dropdown", "")
    ) {
      dd.style.display = "none";
    }
  });
});

// 목록/닫기 버튼 쌍의 표시 여부를 토글하는 공통 헬퍼 (펼쳐졌는지 여부 반환)
function toggleListVisibility(listEl, closeBtn) {
  const opening = listEl.style.display === "none";
  listEl.style.display = opening ? "flex" : "none";
  closeBtn.style.display = opening ? "block" : "none";
  return opening;
}

// 성가대 미리보기 레이아웃 토글
function toggleChoirPreview() {
  toggleListVisibility($("choir-preview-list"), $("choir-preview-close"));
}

// 성경 미리보기 레이아웃 토글
function toggleScripturePreview() {
  const tog = $("sc-preview-toggle");
  const opening = toggleListVisibility(
    $("sc-slide-preview"),
    $("sc-preview-close"),
  );
  tog.textContent = opening
    ? "▼ 슬라이드 분할 미리보기"
    : "▶ 슬라이드 분할 미리보기";
}

// 초기 로딩 진입점 호출
document.addEventListener("DOMContentLoaded", () => {
  init().then(renderCfgSlots);
});
