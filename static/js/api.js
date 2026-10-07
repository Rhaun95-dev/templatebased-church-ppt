/**
 * 공용 API 헬퍼 (service.js / app.js보다 먼저 로드)
 */

// DOM 조회 단축 헬퍼
const $ = (id) => document.getElementById(id);

// 401이면 로그인 오버레이를 띄우고 중단
async function apiFetch(url, options) {
  const res = await fetch(url, options);
  if (res.status === 401) {
    showLogin();
    throw new Error("로그인이 필요해요");
  }
  return res;
}

// JSON POST 요청 공용 헬퍼
async function postJSON(url, body) {
  const res = await apiFetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return res.json();
}
