/* R2a: pogledi umjesto jedne stranice (Rad, Kvaliteta, Knjiga, Alati) + donja navigacija.
 * Ne mijenja main.js: slusa promjenu aktivnog taba (MutationObserver) pa se pogled prebaci
 * i kad tab prebaci JS (npr. switchTab("tab-review")). id-evi i data-tab ostaju isti. */
(function () {
    "use strict";

    var GROUPS = {
        kvaliteta: ["tab-quality"],
        knjiga: ["tab-epub", "tab-review", "tab-history"],
        alati: ["panel-stil", "panel-tts-filter", "tab-expert", "tab-monitor"],
    };
    var VIEWS = ["rad", "kvaliteta", "knjiga", "alati"];
    var lastTab = {};

    function groupOf(tabId) {
        for (var g in GROUPS) {
            if (GROUPS[g].indexOf(tabId) >= 0) return g;
        }
        return null;
    }

    function activeTab() {
        var b = document.querySelector(".tab-btn.active");
        return b ? b.getAttribute("data-tab") : null;
    }

    function currentView() {
        return document.body.getAttribute("data-view") || "rad";
    }

    function markNav(view) {
        var btns = document.querySelectorAll("#bottom-nav .bn-btn");
        for (var i = 0; i < btns.length; i++) {
            var on = btns[i].getAttribute("data-view") === view;
            btns[i].classList.toggle("active", on);
            if (on) btns[i].setAttribute("aria-current", "page");
            else btns[i].removeAttribute("aria-current");
        }
    }

    function setView(view) {
        if (VIEWS.indexOf(view) < 0) view = "rad";
        document.body.setAttribute("data-view", view);
        markNav(view);
        if (view !== "rad") {
            var ids = GROUPS[view];
            if (ids.indexOf(activeTab()) < 0) {
                var want = lastTab[view] && ids.indexOf(lastTab[view]) >= 0 ? lastTab[view] : ids[0];
                var btn = document.querySelector('.tab-btn[data-tab="' + want + '"]');
                if (btn) btn.click();
            }
        }
        try { window.scrollTo(0, 0); } catch (e) { /* nema scrolla */ }
    }

    function onTabChange() {
        var t = activeTab();
        var g = groupOf(t);
        if (!g) return;
        lastTab[g] = t;
        if (g !== currentView()) setView(g);
    }

    function init() {
        if (!document.body.getAttribute("data-view")) document.body.setAttribute("data-view", "rad");
        markNav(currentView());
        var nav = document.getElementById("bottom-nav");
        if (nav) {
            nav.addEventListener("click", function (ev) {
                var b = ev.target.closest ? ev.target.closest(".bn-btn") : null;
                if (b) setView(b.getAttribute("data-view"));
            });
        }
        var tabs = document.querySelector(".tab-nav");
        if (tabs && window.MutationObserver) {
            new MutationObserver(onTabChange).observe(tabs, {
                subtree: true,
                attributes: true,
                attributeFilter: ["class"],
            });
        }
        window.BooklyfiViews = { setView: setView, getView: currentView };
    }

    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
    else init();
})();
