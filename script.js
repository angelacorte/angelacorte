const root = document.documentElement;
const toggle = document.querySelector(".theme-toggle");
const themeColor = document.querySelector('meta[name="theme-color"]');
const storedTheme = localStorage.getItem("theme");
const preferredTheme = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";

function applyTheme(theme) {
  const isDark = theme === "dark";
  root.dataset.theme = theme;
  toggle.setAttribute("aria-pressed", String(isDark));
  toggle.setAttribute("aria-label", `Switch to ${isDark ? "light" : "dark"} theme`);
  themeColor.setAttribute("content", isDark ? "#111820" : "#fbfcfe");
}

applyTheme(storedTheme || preferredTheme);

toggle.addEventListener("click", () => {
  const nextTheme = root.dataset.theme === "dark" ? "light" : "dark";
  localStorage.setItem("theme", nextTheme);
  applyTheme(nextTheme);
});

document.querySelector("#year").textContent = new Date().getFullYear();
