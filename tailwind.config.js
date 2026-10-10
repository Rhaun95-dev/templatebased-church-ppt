/** 시안 A (딥 네이비 + 일렉트릭 블루). 색은 static/src/input.css 의 CSS 변수를 가리킨다. */
module.exports = {
  content: ["./templates/**/*.html", "./static/js/**/*.js"],
  theme: {
    extend: {
      colors: {
        surface: "var(--surface)",
        raised: "var(--surface-raised)",
        ink: "var(--ink)",
        muted: "var(--muted)",
        line: "var(--line)",
        brand: "var(--brand)",
        "on-brand": "var(--on-brand)",
        "brand-text": "var(--brand-text)",
        "brand-soft": "var(--brand-soft)",
        success: "var(--success)",
        danger: "var(--danger)",
      },
      borderRadius: {
        sm: "6px",
        md: "10px",
        lg: "14px",
      },
      fontFamily: {
        sans: [
          '"Noto Sans KR"',
          '"Apple SD Gothic Neo"',
          '"Malgun Gothic"',
          "system-ui",
          "sans-serif",
        ],
      },
      boxShadow: {
        card: "0 8px 24px #00000026",
        focus: "0 0 0 3px #2a62f566",
      },
    },
  },
};
