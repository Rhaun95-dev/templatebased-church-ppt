/**
 * ══════════════════════════════════════════════════
 * UI Interactions & Event Brawling
 * ══════════════════════════════════════════════════
 */

// 탭 전환 핸들러 (찬송가 / 성가대 / 성경 구절, 그리고 헤더 톱니바퀴의 설정)
let lastMainTab = "hymn";

function showPanel(name) {
  document
    .querySelectorAll(".tab-panel")
    .forEach((p) => p.classList.toggle("active", p.id === "tab-" + name));
  document
    .querySelectorAll(".tab-btn")
    .forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  const settings = name === "settings";
  // 설정 화면에서는 탭 바와 PPT 생성 영역을 숨긴다
  $("tabs").classList.toggle("hidden", settings);
  $("generate-bar").classList.toggle("hidden", settings);
  $("settings-btn").setAttribute("aria-pressed", String(settings));
}

function switchTab(name) {
  lastMainTab = name;
  showPanel(name);
}

// 헤더 톱니바퀴: 설정을 열고, 다시 누르면 보던 탭으로 돌아간다
function toggleSettings() {
  const open = $("tab-settings").classList.contains("active");
  showPanel(open ? lastMainTab : "settings");
}

// 화면 테마 (navy-dark / navy-light)
function setTheme(name) {
  document.documentElement.dataset.theme = name;
  try {
    localStorage.setItem("theme", name);
  } catch (e) {}
  markThemeButtons();
}

function markThemeButtons() {
  const cur = document.documentElement.dataset.theme;
  document.querySelectorAll("[data-theme-btn]").forEach((b) => {
    b.classList.toggle("btn-gold", b.dataset.themeBtn === cur);
    b.classList.toggle("btn-outline", b.dataset.themeBtn !== cur);
  });
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

// 초기 로딩 진입점 호출
document.addEventListener("DOMContentLoaded", () => {
  markThemeButtons();
  markThemeButtons();
  updateHymnStatus();
  HymnLibrary.restoreIfGranted().then((ok) => ok && updateHymnStatus());
  TemplateLibrary.restore().then(() => updateTemplateStatus());
  init().then(renderCfgSlots);
});

// 로그인 오버레이
function showLogin() {
  $("login-overlay").style.display = "flex";
  $("login-password").focus();
}

async function submitLogin() {
  const res = await fetch("/api/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password: $("login-password").value }),
  });
  if (res.ok) {
    $("login-overlay").style.display = "none";
    $("login-password").value = "";
    $("login-error").textContent = "";
    init().then(renderCfgSlots);
    return;
  }
  $("login-error").textContent = (await res.json()).error || "로그인 실패";
}
