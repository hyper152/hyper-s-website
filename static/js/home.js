"use strict";
document.getElementById("year").textContent = new Date().getFullYear();
const account = document.querySelector(".account");
document.addEventListener("click", (event) => {
    if (!account.contains(event.target)) account.open = false;
});
document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && account.open) {
        account.open = false;
        account.querySelector("summary").focus();
    }
});
async function initAccount() {
    try {
        const status = await Auth.checkLoginStatus();
        if (status.isLogin) {
            document.getElementById("usernameDisplay").textContent = status.user.username || "用户";
            document.getElementById("loginItem").hidden = true;
            document.getElementById("registerItem").hidden = true;
            document.getElementById("logoutItem").hidden = false;
        }
    } catch (error) {
        console.warn("登录状态暂时不可用", error);
    }
}
document.getElementById("logoutItem").addEventListener("click", async () => {
    const result = await Auth.logout();
    if (result.success) window.location.reload();
});
async function loadVisitCount() {
    const number = document.getElementById("heroVisitNumber");
    const unit = document.getElementById("heroVisitUnit");
    const retry = document.getElementById("retryVisitCount");
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 8000);
    number.textContent = "加载中…";
    unit.hidden = true;
    retry.hidden = true;
    try {
        const response = await fetch(`/visit-count?t=${Date.now()}`, {
            cache: "no-store",
            signal: controller.signal,
        });
        if (!response.ok) throw new Error("访问统计请求失败");
        const data = await response.json();
        const rawCount = data?.data?.total_visits ?? data?.data?.count ?? data?.total_visits ?? data?.count;
        const count = Number(rawCount);
        if (rawCount == null || rawCount === "" || !Number.isSafeInteger(count) || count < 0) {
            throw new Error("访问统计格式无效");
        }
        number.textContent = count.toLocaleString("zh-CN");
        unit.hidden = false;
        const label = document.getElementById("visitCount");
        label.textContent = ` · ${count.toLocaleString("zh-CN")} 次来访`;
        label.hidden = false;
    } catch {
        number.textContent = "暂时不可用";
        retry.hidden = false;
    } finally {
        clearTimeout(timeout);
    }
}
document.getElementById("retryVisitCount").addEventListener("click", loadVisitCount);
loadVisitCount();
initAccount();

const backToTop = document.getElementById("backToTopBtn");
function updateBackToTop() {
    backToTop.hidden = window.scrollY < 300;
}
window.addEventListener("scroll", updateBackToTop, { passive: true });
updateBackToTop();
backToTop.addEventListener("click", () => {
    window.scrollTo({ top: 0, behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth" });
});
