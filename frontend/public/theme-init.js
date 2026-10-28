// Apply the saved theme before the first paint, so a dark choice never flashes light.
try {
  var t = localStorage.getItem("wd_theme");
  if (t === "light" || t === "dark") document.documentElement.setAttribute("data-theme", t);
} catch (e) { /* storage blocked: follow the system */ }
