/* R4: live status (human-timeline) je sklopiv: zadano vidljiv samo trenutni korak; dodir na naslov otvara/zatvara.
 * main.js se ne mijenja: element stvara main.js, ovdje se samo dodaje klasa "collapsed" i prati klik. */
(function () {
    "use strict";
    var KEY = "bf_timeline_open";

    function wasOpen() {
        try { return localStorage.getItem(KEY) === "1"; } catch (e) { return false; }
    }

    function save(open) {
        try { localStorage.setItem(KEY, open ? "1" : "0"); } catch (e) { /* bez pohrane */ }
    }

    function apply() {
        var el = document.getElementById("human-timeline");
        if (!el || el.getAttribute("data-r4")) return;
        el.setAttribute("data-r4", "1");
        if (!wasOpen()) el.classList.add("collapsed");
    }

    function init() {
        apply();
        var dp = document.getElementById("dashboard-panel");
        if (dp && window.MutationObserver) {
            new MutationObserver(apply).observe(dp, { childList: true });
        }
        document.addEventListener("click", function (ev) {
            var t = ev.target && ev.target.closest ? ev.target.closest(".human-timeline .timeline-title") : null;
            if (!t) return;
            var el = document.getElementById("human-timeline");
            if (!el) return;
            save(!el.classList.toggle("collapsed"));
        });
    }

    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
    else init();
})();
