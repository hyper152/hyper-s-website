(() => {
    "use strict";

    const library = window.ACM_LIBRARY;
    const $ = (id) => document.getElementById(id);
    if (!library || !Array.isArray(library.items)) {
        $("results-summary").textContent = "练习记录暂未载入，请刷新页面重试。";
        return;
    }

    const items = library.items;
    const byId = new Map(items.map((item) => [item.id, item]));
    const sourceButtons = [...document.querySelectorAll("[data-source-filter]")];
    const categoryOrder = [
        "动态规划",
        "图与树",
        "数学与数论",
        "数据结构",
        "字符串",
        "贪心与双指针",
        "构造",
        "枚举与位运算",
        "计算几何",
        "模拟与实现",
        "交互",
        "待补全",
    ];
    const params = new URLSearchParams(location.search);
    const filters = {
        category: params.get("category") || "",
        source: params.get("source") || "",
    };
    let opener;
    let toastTimer;

    function element(tag, className, text) {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined) node.textContent = text;
        return node;
    }

    function dateKey(item) {
        return /^\d{4}(?:-\d{2}){0,2}$/.test(item.date || "") ? item.date : "";
    }

    function monthLabel(month) {
        if (!month) return "日期未注明";
        const [year, number] = month.split("-");
        return number ? `${year} 年 ${Number(number)} 月` : `${year} 年`;
    }

    function syncUrl() {
        const url = new URL(location.href);
        for (const key of ["q", "status", "saved", "sort"]) url.searchParams.delete(key);
        const values = { category: filters.category, source: filters.source };
        Object.entries(values).forEach(([key, value]) => {
            if (value) url.searchParams.set(key, value);
            else url.searchParams.delete(key);
        });
        history.replaceState(null, "", url);
    }

    function renderCategories() {
        const fragment = document.createDocumentFragment();
        const categories = [
            "",
            ...categoryOrder.filter((category) => items.some((item) => item.category === category)),
        ];
        categories.forEach((category) => {
            const button = element("button", "acm-category");
            const count = category
                ? items.filter((item) => item.category === category).length
                : items.length;
            button.type = "button";
            button.setAttribute("aria-pressed", String(category === filters.category));
            button.append(
                element("span", "", category || "全部记录"),
                element("small", "", String(count).padStart(2, "0")),
            );
            button.addEventListener("click", () => {
                filters.category = category;
                renderCategories();
                renderProblems();
                syncUrl();
            });
            fragment.append(button);
        });
        $("category-list").replaceChildren(fragment);
    }

    function renderSources() {
        sourceButtons.forEach((button) => {
            button.setAttribute(
                "aria-pressed",
                String(button.dataset.sourceFilter === filters.source),
            );
        });
    }

    function filteredProblems() {
        return items
            .filter((item) => {
                if (filters.category && item.category !== filters.category) return false;
                if (filters.source && item.group !== filters.source) return false;
                return true;
            })
            .sort((first, second) => dateKey(second).localeCompare(dateKey(first)));
    }

    function problemRow(item) {
        const row = element("article", "acm-problem");
        const date = dateKey(item);
        const stamp = element(
            date ? "time" : "span",
            "acm-problem-index",
            date ? date.slice(5).replace("-", ".") || date : "—",
        );
        if (date) stamp.dateTime = date;
        else stamp.setAttribute("aria-label", "日期未注明");

        const button = element("button", "acm-problem-main");
        button.type = "button";
        button.setAttribute("aria-haspopup", "dialog");
        button.append(element("span", "acm-problem-title", item.title));
        const meta = element("span", "acm-problem-meta");
        meta.append(
            element("span", "", item.source),
            element("span", "", `${item.versions.length} 份源码${item.statement ? " · 题面" : ""}`),
        );
        (item.tags || [])
            .slice(0, 2)
            .forEach((tag) => meta.append(element("span", "acm-problem-tag", tag)));
        button.append(meta);
        button.addEventListener("click", () => openProblem(item.id, button));
        row.append(stamp, button);
        return row;
    }

    function renderProblems() {
        const visible = filteredProblems();
        const groups = new Map();
        visible.forEach((item) => {
            const month = dateKey(item).slice(0, 7);
            if (!groups.has(month)) groups.set(month, []);
            groups.get(month).push(item);
        });
        const fragment = document.createDocumentFragment();
        groups.forEach((entries, month) => {
            const group = element("section", "acm-log-group");
            const heading = element("h3", "acm-log-group-heading");
            const date = element(month ? "time" : "span", "", monthLabel(month));
            if (month) date.dateTime = month;
            heading.append(date, element("span", "", `${entries.length} 条记录`));
            group.append(heading);
            entries.forEach((item) => group.append(problemRow(item)));
            fragment.append(group);
        });
        $("problem-list").replaceChildren(fragment);
        $("results-summary").replaceChildren(
            element("strong", "", `${visible.length} 条`),
            document.createTextNode(
                ` / ${items.length} 条练习记录${filters.category ? ` · ${filters.category}` : ""}`,
            ),
        );
        $("empty-state").hidden = visible.length !== 0;
    }

    function toast(message) {
        clearTimeout(toastTimer);
        $("toast").textContent = message;
        $("toast").classList.add("is-visible");
        toastTimer = setTimeout(() => $("toast").classList.remove("is-visible"), 2600);
    }

    async function copyCode(code) {
        try {
            if (!navigator.clipboard || !window.isSecureContext)
                throw new Error("clipboard unavailable");
            await navigator.clipboard.writeText(code);
            toast("代码已复制");
        } catch {
            const area = element("textarea");
            area.value = code;
            area.style.cssText = "position:fixed;opacity:0;left:0;top:0;";
            $("reader").append(area);
            area.select();
            try {
                toast(document.execCommand("copy") ? "代码已复制" : "请选中代码后复制");
            } catch {
                toast("请选中代码后复制");
            }
            area.remove();
        }
    }

    function openProblem(id, trigger) {
        const item = byId.get(id);
        if (!item) return;
        const content = document.createDocumentFragment();
        const heading = element("div", "acm-reader-heading");
        const source = element("div", "acm-reader-source");
        source.append(
            element("span", "", item.date || "日期未注明"),
            element("span", "", item.source),
        );
        const title = element("h2", "", item.title);
        title.id = "reader-title";
        const tags = element("div", "acm-reader-tags");
        [item.category, ...(item.tags || [])].forEach((tag) =>
            tags.append(element("span", "", tag)),
        );
        heading.append(source, title, tags);
        content.append(heading);

        const layout = element("div", "acm-reader-layout");
        const notes = element("div", "acm-reading-notes");
        if (item.summary)
            notes.append(element("h3", "", "解题思路"), element("p", "", item.summary));
        if (item.caution) {
            const caution = element("div", "acm-reading-caution");
            caution.append(
                element("strong", "", "代码备注"),
                document.createTextNode(item.caution),
            );
            notes.append(caution);
        }
        if (item.statement) {
            const details = element("details");
            details.append(element("summary", "", "查看题目海报"));
            const link = element("a");
            link.href = item.statement;
            link.target = "_blank";
            link.rel = "noopener noreferrer";
            const image = element("img");
            image.src = item.statement;
            image.alt = `${item.title}的题目海报`;
            image.loading = "lazy";
            image.decoding = "async";
            link.append(image);
            details.append(link, element("small", "", "点击图片查看完整题面。"));
            notes.append(details);
        }
        if (item.editorial) {
            const details = element("details");
            details.append(
                element("summary", "", "查看参考注释与推导"),
                element("pre", "acm-editorial-text", item.editorial),
            );
            if (item.editorialSource) details.append(element("small", "", item.editorialSource));
            notes.append(details);
        }
        if (item.links?.length) {
            const links = element("div", "acm-reading-links");
            item.links.forEach(({ label, url }) => {
                const link = element("a", "", `${label} ↗`);
                link.href = url;
                link.target = "_blank";
                link.rel = "noopener noreferrer";
                links.append(link);
            });
            notes.append(links);
        }

        const panel = element("div", "acm-source-panel");
        const tools = element("div", "acm-source-tools");
        const versions = element("select");
        versions.setAttribute("aria-label", "选择源码版本");
        item.versions.forEach((version, index) => {
            const duplicate = item.versions.some(
                (other, otherIndex) =>
                    otherIndex !== index &&
                    other.name === version.name &&
                    other.language === version.language,
            );
            const filename = version.path.split("/").pop();
            const phase = version.path.includes("/upsolve/")
                ? "补题"
                : item.group === "icpc"
                  ? "赛时"
                  : "原存档";
            const suffix = duplicate ? ` · ${phase} / ${filename}` : "";
            const option = element("option", "", `${version.name} · ${version.language}${suffix}`);
            option.value = index;
            versions.append(option);
        });
        const copy = element("button", "acm-copy", "复制代码");
        copy.type = "button";
        copy.addEventListener("click", () =>
            copyCode(item.versions[Number(versions.value)]?.code || ""),
        );
        tools.append(versions, copy);
        const path = element("p", "acm-source-path");
        const notice = element("div", "acm-version-notice");
        const pre = element("pre", "acm-source-code");
        const code = element("code");
        pre.append(code);
        const messages = {
            empty: "原文件为空。",
            incomplete: "保留原稿中的未完成实现。",
            error: "来自原题档的 ERROR 目录，保留当时的错误版本。",
            "ac-directory": "来自原题档的 AC 目录。",
            reference: "AI 参考版本，保留原注释。",
            original: "个人练习原稿。",
        };
        function renderVersion() {
            const version = item.versions[Number(versions.value)];
            versions.hidden = !version;
            copy.disabled = !version?.code;
            path.textContent = version ? `题档 / ${version.path}` : "";
            code.textContent = version?.code || "// 原题档暂未包含代码。";
            notice.textContent = version ? messages[version.status] || "原题档存档。" : "";
            notice.hidden = !version;
            pre.scrollTop = 0;
            pre.scrollLeft = 0;
        }
        versions.addEventListener("change", renderVersion);
        panel.append(tools, path, notice, pre);
        renderVersion();
        layout.append(notes, panel);
        content.append(layout);
        $("reader-content").replaceChildren(content);
        $("reader-breadcrumb").textContent = `PRACTICE LOG / ${item.source}`;
        opener = trigger || document.activeElement;
        $("reader").showModal();
        $("reader").scrollTop = 0;
        $("reader-close").focus({ preventScroll: true });
    }

    if (!categoryOrder.includes(filters.category)) filters.category = "";
    if (!sourceButtons.some((button) => button.dataset.sourceFilter === filters.source))
        filters.source = "";
    sourceButtons.forEach((button) => {
        button.addEventListener("click", () => {
            filters.source = button.dataset.sourceFilter;
            renderSources();
            renderProblems();
            syncUrl();
        });
    });
    $("clear-filters").addEventListener("click", () => {
        Object.assign(filters, { category: "", source: "" });
        renderCategories();
        renderSources();
        renderProblems();
        syncUrl();
    });
    $("reader-close").addEventListener("click", () => $("reader").close());
    $("reader").addEventListener("close", () => {
        if (opener?.isConnected) opener.focus({ preventScroll: true });
    });
    $("reader").addEventListener("click", (event) => {
        if (event.target !== $("reader")) return;
        const bounds = $("reader").getBoundingClientRect();
        if (
            event.clientX < bounds.left ||
            event.clientX > bounds.right ||
            event.clientY < bounds.top ||
            event.clientY > bounds.bottom
        )
            $("reader").close();
    });
    $("total-problems").textContent = items.length;
    $("total-versions").textContent = items.reduce(
        (count, item) => count + item.versions.length,
        0,
    );
    $("total-categories").textContent = new Set(items.map((item) => item.category)).size;
    $("total-posters").textContent = items.filter((item) => item.statement).length;
    renderCategories();
    renderSources();
    renderProblems();
    syncUrl();
})();
