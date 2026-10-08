// /pages/visit/ 访问分析页面：读取 /api/visit-stats 并渲染总览、地区与排行。
(() => {
    'use strict';

    const API = '/api/visit-stats';
    const LOGIN_URL = '/pages/login/index.html?redirect=%2Fpages%2Fvisit%2F';
    // 每个地区 entries: [IP, 访问次数, 登录用户列表, 最后访问时间]
    const IP_INDEX = 0;
    const VISITS_INDEX = 1;
    const USERS_INDEX = 2;
    const LAST_SEEN_INDEX = 3;
    // 地区默认只列前 12 个，其余点按钮展开，避免页面被几百行撑得过长。
    const REGION_PREVIEW = 12;

    const dom = {
        headingRecords: document.getElementById('headingRecords'),
        generatedAt: document.getElementById('generatedAt'),
        visitRange: document.getElementById('visitRange'),
        detailHint: document.getElementById('detailHint'),
        detailHintSep: document.getElementById('detailHintSep'),
        filterStatus: document.getElementById('filterStatus'),
        alert: document.getElementById('visitAlert'),
        filter: document.getElementById('visitFilter'),
        refresh: document.getElementById('refreshStats'),
        cards: {
            records: document.getElementById('cardRecords'),
            range: document.getElementById('cardRange'),
            ips: document.getElementById('cardIps'),
            ipsSplit: document.getElementById('cardIpsSplit'),
            domestic: document.getElementById('cardDomestic'),
            domesticShare: document.getElementById('cardDomesticShare'),
            errors: document.getElementById('cardErrors'),
            errorShare: document.getElementById('cardErrorShare'),
        },
        trend: document.getElementById('trendChart'),
        trendNote: document.getElementById('trendNote'),
        domestic: document.getElementById('domesticList'),
        domesticNote: document.getElementById('domesticNote'),
        overseas: document.getElementById('overseasList'),
        overseasNote: document.getElementById('overseasNote'),
        internal: document.getElementById('internalList'),
        internalNote: document.getElementById('internalNote'),
        topIps: document.getElementById('topIpBody'),
        paths: document.getElementById('pathList'),
        locked: document.getElementById('lockedPanel'),
        lockedTitle: document.getElementById('lockedTitle'),
        lockedMessage: document.getElementById('lockedMessage'),
        loginLink: document.getElementById('loginLink'),
        dialog: document.getElementById('visitDialog'),
        detailTitle: document.getElementById('detailTitle'),
        detailSub: document.getElementById('detailSub'),
        detailBody: document.getElementById('detailBody'),
        detailCopy: document.getElementById('detailCopy'),
        detailClose: document.getElementById('detailClose'),
        toast: document.getElementById('visitToast'),
        year: document.getElementById('visitYear'),
    };

    const state = { payload: null, filter: '', expanded: {} };
    const detailState = { ip: '', offset: 0, loading: false };

    const number = (value) => (value || 0).toLocaleString('zh-CN');
    const escapeHtml = (text) => String(text).replace(/[&<>"']/g,
        (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
    const shortTime = (text) => (text ? String(text).slice(0, 16) : '—');
    const share = (part, total) => (total ? `${(part / total * 100).toFixed(1)}%` : '—');
    // Windows 浏览器不渲染国旗 emoji（🇨🇳 会显示成 “CN”），页面里统一去掉前缀图标。
    const REGION_PREFIX = /^(?:🇨🇳|🌍|⚠️|🏠)\s*/u;
    const regionName = (label) => String(label || '').replace(REGION_PREFIX, '');

    let toastTimer = 0;
    function toast(message) {
        dom.toast.textContent = message;
        dom.toast.hidden = false;
        window.clearTimeout(toastTimer);
        toastTimer = window.setTimeout(() => { dom.toast.hidden = true; }, 1800);
    }

    function showAlert(message) {
        dom.alert.textContent = message;
        dom.alert.hidden = !message;
    }

    function showLocked(title, message) {
        document.body.classList.add('is-locked');
        dom.locked.hidden = false;
        dom.lockedTitle.textContent = title;
        dom.lockedMessage.textContent = message;
        dom.headingRecords.textContent = '';
    }

    // 详细记录只对白名单账号（默认 hyper）开放，其他账号点 IP 只会看到提示。
    function canViewDetail() {
        return Boolean(state.payload && state.payload.viewer && state.payload.viewer.can_view_detail);
    }

    // 会话既可能在 Cookie 里，也可能存在 localStorage，两者都带上更稳妥。
    function authHeaders() {
        let sessionId = '';
        try {
            sessionId = window.localStorage.getItem('session_id') || '';
        } catch {
            sessionId = '';
        }
        return sessionId ? { Authorization: `Session ${sessionId}` } : {};
    }

    function renderCards(payload) {
        const totals = payload.totals;
        dom.cards.records.textContent = number(totals.records);
        dom.cards.range.textContent = `${shortTime(totals.first_visit)} → ${shortTime(totals.last_visit)}`;
        dom.cards.ips.textContent = number(totals.ips);
        dom.cards.ipsSplit.textContent =
            `国内 ${number(totals.domestic_ips)} · 国外 ${number(totals.overseas_ips)} · 内网 ${number(totals.internal_ips)}`;
        dom.cards.domestic.textContent = number(totals.domestic_visits);
        dom.cards.domesticShare.textContent = `占全部 ${share(totals.domestic_visits, totals.records)}`;
        dom.cards.errors.textContent = number(totals.errors);
        dom.cards.errorShare.textContent = `占全部 ${share(totals.errors, totals.records)}（4xx / 5xx）`;
        dom.headingRecords.textContent = `${number(totals.records)} 条记录`;
    }

    function renderTrend(daily) {
        const max = daily.reduce((top, day) => Math.max(top, day.visits), 0);
        dom.trend.innerHTML = daily.map((day, index) => {
            const height = max ? Math.max(Math.round(day.visits / max * 100), day.visits ? 4 : 1) : 1;
            const label = index % 5 === 0 || index === daily.length - 1 ? day.date.slice(5) : '';
            return `<div class="trend-bar" data-empty="${day.visits ? 0 : 1}" title="${day.date}：${number(day.visits)} 次">`
                + `<i style="height:${height}%"></i>${label ? `<span>${label}</span>` : ''}</div>`;
        }).join('');
        const total = daily.reduce((sum, day) => sum + day.visits, 0);
        dom.trendNote.textContent = `${daily.length} 天共 ${number(total)} 次 · 峰值 ${number(max)} 次`;
    }

    function regionItemHtml(region, maxVisits, open) {
        const width = maxVisits ? Math.max(Math.round(region.visits / maxVisits * 100), 2) : 2;
        const hint = canViewDetail() ? '点击查看详细记录' : '登录 hyper 账号后可查看详细记录';
        const chips = region.entries.map((entry) => {
            const ip = entry[IP_INDEX];
            const users = entry[USERS_INDEX] || [];
            const userTag = users.length
                ? `<span class="ip-user">${escapeHtml(users.join(', '))}</span>` : '';
            return `<button class="ip-chip" type="button" data-ip="${escapeHtml(ip)}"`
                + ` data-search="${escapeHtml(`${ip} ${users.join(' ')}`.toLowerCase())}"`
                + ` title="${hint}｜最后访问 ${escapeHtml(shortTime(entry[LAST_SEEN_INDEX]))}">`
                + `<span class="ip-text">${escapeHtml(ip)}</span>${userTag}`
                + `<span class="ip-count">${number(entry[VISITS_INDEX])} 次</span></button>`;
        }).join('');
        return `<details class="region-item" data-search="${escapeHtml(region.label.toLowerCase())}"${open ? ' open' : ''}>`
            + '<summary>'
            + `<span class="region-label">${escapeHtml(regionName(region.label))}</span>`
            + `<span class="region-bar"><i style="width:${width}%"></i></span>`
            + `<span class="region-stats">${number(region.ips)} IP · ${number(region.visits)} 次</span>`
            + '</summary>'
            + `<div class="ip-grid">${chips}</div>`
            + '</details>';
    }

    function renderRegionList(container, regions, options) {
        const { key = '', emptyText = '暂无记录', preview = true } = options || {};
        if (!regions.length) {
            container.innerHTML = `<p class="empty">${escapeHtml(emptyText)}</p>`;
            return;
        }
        const maxVisits = regions.reduce((top, region) => Math.max(top, region.visits), 0);
        // 搜索时展开全部，否则只渲染前 REGION_PREVIEW 个地区。
        const expanded = Boolean(state.filter) || state.expanded[key];
        const shown = preview && !expanded ? regions.slice(0, REGION_PREVIEW) : regions;
        // 默认全部折叠，点击省份再看具体 IP，页面高度保持在可控范围。
        let html = shown.map((region) => regionItemHtml(region, maxVisits, false)).join('');

        // 搜索时展示全部地区，此时不再显示展开/收起按钮。
        if (preview && !state.filter && regions.length > REGION_PREVIEW) {
            html += expanded
                ? `<button class="region-more" type="button" data-key="${key}" data-collapse="1">`
                    + `收起，只显示前 ${REGION_PREVIEW} 个地区</button>`
                : `<button class="region-more" type="button" data-key="${key}">`
                    + `显示其余 ${regions.length - REGION_PREVIEW} 个地区（共 ${regions.length} 个）</button>`;
        }
        container.innerHTML = html;
    }

    function renderTopIps(topIps) {
        dom.topIps.innerHTML = topIps.map((item, index) => {
            const users = (item.users || []).join(', ') || '游客';
            const region = regionName(item.region);
            return `<tr data-search="${escapeHtml(`${item.ip} ${region} ${users}`.toLowerCase())}">`
                + `<td class="rank">${index + 1}</td>`
                + `<td class="is-ip">${escapeHtml(item.ip)}</td>`
                + `<td>${escapeHtml(region)}</td>`
                + `<td>${number(item.visits)}</td>`
                + `<td>${escapeHtml(users)}</td>`
                + `<td>${escapeHtml(shortTime(item.last_seen))}</td></tr>`;
        }).join('');
    }

    function renderPaths(paths) {
        const max = paths.reduce((top, item) => Math.max(top, item.visits), 0);
        dom.paths.innerHTML = paths.map((item) => (
            `<li data-search="${escapeHtml(item.path.toLowerCase())}">`
            + `<span class="path-text" title="${escapeHtml(item.path)}">${escapeHtml(item.path)}</span>`
            + `<span class="path-count">${number(item.visits)} 次 · 占峰值 ${share(item.visits, max)}</span></li>`
        )).join('');
    }

    function applyFilter() {
        const keyword = state.filter.trim().toLowerCase();
        const matches = (text) => !keyword || text.includes(keyword);
        let matchedRegions = 0;
        let matchedChips = 0;

        document.querySelectorAll('.region-item').forEach((item) => {
            const regionHit = matches(item.dataset.search || '');
            let visibleChips = 0;
            item.querySelectorAll('.ip-chip').forEach((chip) => {
                // 地区名命中时直接展示该地区全部 IP，否则按 IP / 用户名过滤。
                const hit = regionHit || matches(chip.dataset.search || '');
                chip.classList.toggle('is-hidden', !hit);
                if (hit) visibleChips += 1;
            });
            const visible = !keyword || regionHit || visibleChips > 0;
            item.classList.toggle('is-hidden', !visible);
            if (keyword && visible) item.open = true;
            if (visible) matchedRegions += 1;
            matchedChips += visibleChips;
            const grid = item.querySelector('.ip-grid');
            if (grid) {
                const empty = grid.querySelector('.empty');
                if (!visibleChips && !empty) {
                    grid.insertAdjacentHTML('beforeend', '<span class="empty">没有匹配的 IP</span>');
                } else if (visibleChips && empty) {
                    empty.remove();
                }
            }
        });

        // 只过滤主页面上的列表，弹窗里的明细表不受搜索框影响。
        document.querySelectorAll('main .visit-table tbody tr, main .path-list li').forEach((row) => {
            row.classList.toggle('is-hidden', !matches(row.dataset.search || ''));
        });

        if (dom.filterStatus) {
            if (!keyword) {
                dom.filterStatus.hidden = true;
                dom.filterStatus.textContent = '';
            } else {
                dom.filterStatus.hidden = false;
                dom.filterStatus.textContent = matchedRegions
                    ? `匹配 ${number(matchedRegions)} 个地区 · ${number(matchedChips)} 个 IP`
                    : '没有匹配的地区或 IP，换个关键词试试';
            }
        }
    }

    function render(payload) {
        state.payload = payload;
        renderCards(payload);
        renderTrend(payload.daily || []);
        renderRegionList(dom.domestic, payload.domestic || [],
            { key: 'domestic', emptyText: '暂无国内访问记录' });
        renderRegionList(dom.overseas, payload.overseas || [],
            { key: 'overseas', emptyText: '暂无国外访问记录' });
        const internal = payload.internal || { ips: 0, visits: 0, entries: [] };
        renderRegionList(dom.internal, internal.ips ? [{
            label: internal.label,
            ips: internal.ips,
            visits: internal.visits,
            entries: internal.entries,
        }] : [], { preview: false, emptyText: '暂无内网访问记录' });
        renderTopIps(payload.top_ips || []);
        renderPaths(payload.top_paths || []);
        dom.domesticNote.textContent = `${payload.domestic.length} 个省份/地区 · 按访问次数降序`;
        dom.overseasNote.textContent = `${payload.overseas.length} 个国家/地区 · 按访问次数降序`;
        dom.internalNote.textContent = `${number(internal.ips)} IP · ${number(internal.visits)} 次`;
        dom.generatedAt.textContent = `生成于 ${payload.generated_at}`;
        dom.visitRange.textContent = `报告：${payload.report_file}`;
        document.body.classList.toggle('no-detail', !canViewDetail());
        if (dom.detailHint) {
            dom.detailHint.textContent = canViewDetail()
                ? '点击任意 IP 查看详细记录'
                : '登录 hyper 账号后可查看 IP 详细记录';
            dom.detailHint.hidden = false;
            if (dom.detailHintSep) dom.detailHintSep.hidden = false;
        }
        applyFilter();
    }

    const DETAIL_PAGE_SIZE = 200;

    async function fetchDetail(ip, offset) {
        const params = new URLSearchParams({ ip, offset: String(offset), limit: String(DETAIL_PAGE_SIZE) });
        const response = await fetch(`/api/visit-detail?${params}`, {
            headers: { Accept: 'application/json', ...authHeaders() },
            credentials: 'include',
            cache: 'no-store',
        });
        if (response.status === 401) {
            throw new Error('登录状态已失效，请重新登录');
        }
        if (response.status === 403) {
            throw new Error('只有 hyper 账号可以查看访客详细记录');
        }
        if (!response.ok) {
            const data = await response.json().catch(() => ({}));
            throw new Error(data.error || `HTTP ${response.status}`);
        }
        return response.json();
    }

    function recordRows(records) {
        return records.map((item) => {
            const status = String(item.status === undefined ? '' : item.status);
            const statusClass = /^[45]/.test(status) ? 'status-error' : 'status-ok';
            const user = item.user && item.user !== '游客' ? item.user : '游客';
            return `<tr><td>${escapeHtml(shortTime(item.time))}</td><td>${escapeHtml(user)}</td>`
                + `<td>${escapeHtml(item.method)}</td>`
                + `<td class="is-path">${escapeHtml(item.path)}</td>`
                + `<td class="${statusClass}">${escapeHtml(status)}</td></tr>`;
        }).join('');
    }

    function updateMoreButton(data) {
        const count = dom.detailBody.querySelector('#detailCount');
        if (count) {
            count.textContent = `已显示 ${number(detailState.offset)} / ${number(data.totals.records)} 条（最新在前）`;
        }
        const button = dom.detailBody.querySelector('#detailMore');
        if (!button) {
            return;
        }
        const rest = data.totals.records - detailState.offset;
        button.hidden = !data.has_more || rest <= 0;
        button.disabled = false;
        if (!button.hidden) {
            button.textContent = `加载更多（还有 ${number(rest)} 条）`;
        }
    }

    function renderDetail(data, append) {
        const totals = data.totals;
        dom.detailSub.textContent = `${regionName(data.region)} · 共 ${number(totals.records)} 条记录`
            + ` · 最后访问 ${shortTime(totals.last_seen)}`;

        if (append) {
            const rows = dom.detailBody.querySelector('#detailRows');
            if (rows) {
                rows.insertAdjacentHTML('beforeend', recordRows(data.records));
            }
            detailState.offset += data.records.length;
            updateMoreButton(data);
            return;
        }

        const location = data.location || {};
        const locationText = [location.country, location.region, location.city, location.isp]
            .filter((value) => value && value !== '未知').join(' · ') || '未知';
        const users = (totals.users || []).length ? totals.users.join(', ') : '游客';
        const methods = (totals.methods || [])
            .map((item) => `${item.method} ${number(item.visits)} 次`).join(' · ') || '—';
        const paths = (data.paths || []).map((item) => (
            `<div><span class="path" title="${escapeHtml(item.path)}">${escapeHtml(item.path)}</span>`
            + `<span class="count">${number(item.visits)} 次`
            + `${item.errors ? ` · ${number(item.errors)} 错误` : ''}</span></div>`
        )).join('');

        dom.detailBody.innerHTML = `
<section class="detail-block">
<h3>概览</h3>
<dl class="detail-grid">
<div><dt>归属地</dt><dd>${escapeHtml(locationText)}</dd></div>
<div><dt>总请求</dt><dd>${number(totals.records)}</dd></div>
<div><dt>错误请求</dt><dd>${number(totals.errors)}</dd></div>
<div><dt>登录用户</dt><dd>${escapeHtml(users)}</dd></div>
<div><dt>首次访问</dt><dd>${escapeHtml(shortTime(totals.first_seen))}</dd></div>
<div><dt>最后访问</dt><dd>${escapeHtml(shortTime(totals.last_seen))}</dd></div>
<div><dt>请求方法</dt><dd>${escapeHtml(methods)}</dd></div>
<div><dt>访问路径</dt><dd>${number(totals.paths)} 个</dd></div>
</dl>
</section>
<section class="detail-block">
<h3>访问最多的路径<span>前 ${(data.paths || []).length} 个</span></h3>
<div class="detail-paths">${paths || '<p class="empty">暂无访问路径</p>'}</div>
</section>
<section class="detail-block">
<h3>详细记录<span id="detailCount"></span></h3>
<div class="detail-records">
<table class="visit-table">
<thead><tr><th scope="col">时间</th><th scope="col">用户</th><th scope="col">方法</th><th scope="col">路径</th><th scope="col">状态</th></tr></thead>
<tbody id="detailRows">${recordRows(data.records)}</tbody>
</table>
</div>
<button class="visit-btn dialog-more" hidden="" id="detailMore" type="button">加载更多</button>
</section>`;

        detailState.offset = data.records.length;
        updateMoreButton(data);
    }

    async function openDetail(ip) {
        detailState.ip = ip;
        detailState.offset = 0;
        dom.detailTitle.textContent = ip;
        dom.detailSub.textContent = '正在加载…';
        dom.detailBody.innerHTML = '<p class="dialog-note">正在加载详细记录…</p>';
        if (!dom.dialog.open) {
            if (typeof dom.dialog.showModal === 'function') {
                dom.dialog.showModal();
            } else {
                dom.dialog.setAttribute('open', '');
            }
        }
        try {
            renderDetail(await fetchDetail(ip, 0), false);
        } catch (error) {
            dom.detailSub.textContent = '';
            dom.detailBody.innerHTML = `<p class="dialog-note">加载失败：${escapeHtml(error.message)}</p>`;
        }
    }

    async function load(force) {
        dom.refresh.disabled = true;
        showAlert('');
        try {
            const response = await fetch(force ? `${API}?refresh=1` : API, {
                headers: { Accept: 'application/json', ...authHeaders() },
                credentials: 'include',
                cache: 'no-store',
            });
            if (response.status === 401) {
                showLocked('需要登录', '访客 IP 属于隐私数据，请登录后查看访问分析。');
                return;
            }
            if (response.status === 403) {
                showLocked('无权查看', '当前账号没有查看访问分析的权限。');
                return;
            }
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            render(await response.json());
        } catch (error) {
            showAlert(`加载访问分析失败：${error.message}。请稍后点击“刷新数据”重试。`);
        } finally {
            dom.refresh.disabled = false;
        }
    }

    function onFilterInput() {
        const keyword = dom.filter.value || '';
        const toggled = Boolean(keyword) !== Boolean(state.filter);
        state.filter = keyword;
        // 搜索范围是全部地区，进入或退出搜索时重新渲染地区列表。
        if (toggled && state.payload) {
            render(state.payload);
        } else {
            applyFilter();
        }
    }

    // 中文输入法组合期间不要过滤，否则拼音中间态会反复重排整页。
    let composing = false;
    dom.filter?.addEventListener('compositionstart', () => { composing = true; });
    dom.filter?.addEventListener('compositionend', () => {
        composing = false;
        onFilterInput();
    });
    dom.filter?.addEventListener('input', (event) => {
        if (composing || event.isComposing) {
            return;
        }
        onFilterInput();
    });

    dom.refresh?.addEventListener('click', () => load(true));

    document.addEventListener('click', async (event) => {
        const more = event.target.closest('.region-more');
        if (more) {
            const key = more.dataset.key || '';
            state.expanded[key] = !more.dataset.collapse;
            if (state.payload) {
                render(state.payload);
            }
            return;
        }
        const moreRecords = event.target.closest('#detailMore');
        if (moreRecords) {
            moreRecords.disabled = true;
            try {
                renderDetail(await fetchDetail(detailState.ip, detailState.offset), true);
            } catch (error) {
                moreRecords.disabled = false;
                toast(error.message);
            }
            return;
        }
        const chip = event.target.closest('.ip-chip');
        if (!chip) {
            return;
        }
        const ip = chip.dataset.ip || '';
        if (!ip) {
            return;
        }
        if (!canViewDetail()) {
            toast(document.body.classList.contains('is-locked')
                ? '请先登录后查看详细记录'
                : '只有 hyper 账号可以查看详细记录');
            return;
        }
        openDetail(ip);
    });

    dom.detailClose?.addEventListener('click', () => dom.dialog.close());

    dom.detailCopy?.addEventListener('click', async () => {
        if (!detailState.ip) {
            return;
        }
        try {
            await navigator.clipboard.writeText(detailState.ip);
            toast(`已复制 ${detailState.ip}`);
        } catch {
            toast(detailState.ip);
        }
    });

    // 点击弹窗外部的遮罩层关闭弹窗。
    dom.dialog?.addEventListener('click', (event) => {
        if (event.target === dom.dialog) {
            dom.dialog.close();
        }
    });

    if (dom.year) {
        dom.year.textContent = String(new Date().getFullYear());
    }
    if (dom.loginLink) {
        dom.loginLink.href = LOGIN_URL;
    }
    load(false);
})();
