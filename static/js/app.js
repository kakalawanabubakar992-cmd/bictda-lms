/* =========================================================================
   BICTDA LMS - shared JavaScript
   Sidebar drawer & collapse, dropdowns, toasts, password toggle,
   intern sign-in tabs and demo-account quick fill.
   ========================================================================= */
(function () {
  "use strict";

  var html = document.documentElement;
  var sidebar = document.getElementById("sidebar");
  var overlay = document.getElementById("sidebar-overlay");

  /* ---------- Sidebar: slide-in drawer on phones ---------- */
  function openSidebar() {
    if (!sidebar) return;
    sidebar.classList.remove("-translate-x-full");
    if (overlay) overlay.classList.remove("hidden");
    document.body.style.overflow = "hidden";
  }
  function closeSidebar() {
    if (!sidebar) return;
    if (window.innerWidth < 1024) sidebar.classList.add("-translate-x-full");
    if (overlay) overlay.classList.add("hidden");
    document.body.style.overflow = "";
  }
  document.querySelectorAll("[data-sidebar-open]").forEach(function (btn) {
    btn.addEventListener("click", openSidebar);
  });
  document.querySelectorAll("[data-sidebar-close]").forEach(function (btn) {
    btn.addEventListener("click", closeSidebar);
  });
  window.addEventListener("resize", function () {
    if (window.innerWidth >= 1024) {
      if (overlay) overlay.classList.add("hidden");
      document.body.style.overflow = "";
    } else if (sidebar && overlay && overlay.classList.contains("hidden")) {
      sidebar.classList.add("-translate-x-full");
    }
  });

  /* ---------- Sidebar: collapse to icons on desktop (remembered) ---------- */
  document.querySelectorAll("[data-sidebar-collapse]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var collapsed = html.classList.toggle("sidebar-collapsed");
      try { localStorage.setItem("bictda-sidebar", collapsed ? "collapsed" : "open"); } catch (e) {}
    });
  });

  /* ---------- Dropdown menus (notifications, profile) ---------- */
  function closeAllDropdowns(except) {
    document.querySelectorAll("[data-dropdown-menu]").forEach(function (menu) {
      if (menu !== except) menu.classList.add("hidden");
    });
  }
  document.querySelectorAll("[data-dropdown]").forEach(function (wrap) {
    var toggle = wrap.querySelector("[data-dropdown-toggle]");
    var menu = wrap.querySelector("[data-dropdown-menu]");
    if (!toggle || !menu) return;
    toggle.addEventListener("click", function (event) {
      event.stopPropagation();
      closeAllDropdowns(menu);
      menu.classList.toggle("hidden");
    });
  });
  document.addEventListener("click", function (event) {
    if (!event.target.closest("[data-dropdown]")) closeAllDropdowns();
  });
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") { closeAllDropdowns(); closeSidebar(); }
  });

  /* ---------- Toast notifications ---------- */
  function dismissToast(toast) {
    if (!toast || toast.classList.contains("toast-out")) return;
    toast.classList.add("toast-out");
    setTimeout(function () { toast.remove(); }, 300);
  }
  function wireToast(toast) {
    var timer = setTimeout(function () { dismissToast(toast); }, 5000);
    var close = toast.querySelector("[data-toast-close]");
    if (close) close.addEventListener("click", function () { clearTimeout(timer); dismissToast(toast); });
  }
  document.querySelectorAll("[data-toast]").forEach(wireToast);

  var TOAST_STYLES = {
    success: ["emerald", "fa-circle-check"],
    error: ["rose", "fa-circle-exclamation"],
    warning: ["amber", "fa-triangle-exclamation"],
    info: ["sky", "fa-circle-info"]
  };

  /* BICTDA.toast("Message", "success") - show a toast from any page script */
  function showToast(message, type, actionLabel, onAction) {
    var stack = document.getElementById("toast-stack");
    if (!stack) return null;
    var style = TOAST_STYLES[type] || TOAST_STYLES.info;
    var toast = document.createElement("div");
    toast.className = "toast pointer-events-auto flex w-full max-w-sm items-start gap-3 rounded-2xl border border-" +
      style[0] + "-200 bg-white/95 p-4 shadow-xl backdrop-blur";
    toast.setAttribute("role", "status");
    toast.innerHTML =
      '<span class="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-' + style[0] + "-100 text-" + style[0] +
      '-600"><i class="fa-solid ' + style[1] + '"></i></span>' +
      '<div class="flex-1 pt-1.5"><p class="text-sm font-medium text-slate-700"></p></div>' +
      '<button type="button" class="rounded-lg p-1 text-slate-400 hover:bg-slate-100" aria-label="Dismiss" data-toast-close>' +
      '<i class="fa-solid fa-xmark"></i></button>';
    toast.querySelector("p").textContent = message;
    if (actionLabel && onAction) {
      var action = document.createElement("button");
      action.type = "button";
      action.className = "mt-2 rounded-lg bg-royal-600 px-3 py-1.5 text-xs font-bold text-white hover:bg-royal-700";
      action.textContent = actionLabel;
      action.addEventListener("click", onAction);
      toast.querySelector("div").appendChild(action);
      toast.querySelector("[data-toast-close]").addEventListener("click", function () { dismissToast(toast); });
    } else {
      var bar = document.createElement("span");
      bar.className = "toast-bar bg-" + style[0] + "-500";
      toast.appendChild(bar);
      wireToast(toast);
    }
    stack.appendChild(toast);
    return toast;
  }
  window.BICTDA = window.BICTDA || {};
  window.BICTDA.toast = showToast;

  /* ---------- Show / hide password ---------- */
  document.querySelectorAll("[data-password-toggle]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var input = document.getElementById(btn.getAttribute("data-password-toggle"));
      if (!input) return;
      var show = input.type === "password";
      input.type = show ? "text" : "password";
      btn.setAttribute("aria-label", show ? "Hide password" : "Show password");
      btn.innerHTML = show ? '<i class="fa-regular fa-eye-slash"></i>' : '<i class="fa-regular fa-eye"></i>';
    });
  });

  /* ---------- Intern sign-in tabs: Email | Intern ID | Phone ---------- */
  var ACTIVE_TAB = ["border-royal-500", "bg-royal-50", "text-royal-700"];
  var IDLE_TAB = ["border-slate-200", "text-slate-500", "hover:border-slate-300", "hover:text-slate-700"];

  function selectLoginTab(tab) {
    var methodInput = document.getElementById("login-method");
    var input = document.getElementById("identifier");
    var label = document.getElementById("identifier-label");
    var icon = document.getElementById("identifier-icon");
    if (!methodInput || !input) return;

    document.querySelectorAll("[data-login-tab]").forEach(function (other) {
      var active = other === tab;
      other.setAttribute("aria-selected", active ? "true" : "false");
      ACTIVE_TAB.forEach(function (c) { other.classList.toggle(c, active); });
      IDLE_TAB.forEach(function (c) { other.classList.toggle(c, !active); });
    });

    methodInput.value = tab.getAttribute("data-login-tab");
    input.type = tab.getAttribute("data-type");
    input.setAttribute("inputmode", tab.getAttribute("data-inputmode"));
    input.placeholder = tab.getAttribute("data-placeholder");
    if (label) label.textContent = tab.getAttribute("data-label");
    if (icon) icon.className = tab.getAttribute("data-icon") + " text-slate-400";
  }

  document.querySelectorAll("[data-login-tab]").forEach(function (tab) {
    tab.addEventListener("click", function () {
      selectLoginTab(tab);
      var input = document.getElementById("identifier");
      if (input) { input.value = ""; input.focus(); }
    });
  });

  /* ---------- Demo account quick fill ---------- */
  document.querySelectorAll("[data-demo-fill]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var method = btn.getAttribute("data-method");
      if (method) {
        var tab = document.querySelector('[data-login-tab="' + method + '"]');
        if (tab) selectLoginTab(tab);
      }
      var identifier = document.getElementById("identifier");
      var password = document.getElementById("password");
      if (identifier) identifier.value = btn.getAttribute("data-id");
      if (password) password.value = btn.getAttribute("data-password");
      showToast("Demo account filled - press Sign In.", "info");
    });
  });
})();
