(() => {
  'use strict';
  const library = window.ACM_LIBRARY;
  const $ = (id) => document.getElementById(id);
  if (!library || !Array.isArray(library.items)) {
    $('results-summary').textContent = '题库暂未载入，请刷新页面重试。';
    return;
  }
  const items = library.items;
  const byId = new Map(items.map((item) => [item.id, item]));
  const storageKey = 'hyper.acm.review.v1';
  const statuses = { todo: '未复习', review: '再练一次', mastered: '已掌握' };
  const levels = { '基础': 0, '进阶': 1, '挑战': 2, '待补全': 3 };
  const categoryOrder = ['动态规划', '图与树', '数学与数论', '数据结构', '字符串', '贪心与双指针', '构造', '枚举与位运算', '计算几何', '模拟与实现', '交互', '待补全'];
  let records = {};
  let storageAvailable = true;
  let readerItem = null;
  let searchTimer;
  let toastTimer;
  let noteTimer;
  let notePending = null;
  let opener = null;
  const params = new URLSearchParams(location.search);
  const filters = { query: params.get('q') || '', category: params.get('category') || '', source: params.get('source') || '', status: params.get('status') || '', favorites: params.get('saved') === '1', sort: params.get('sort') || 'recent' };

  function element(tag, className, text) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (text !== undefined) el.textContent = text;
    return el;
  }

  function sanitizeRecords(value) {
    const output = {};
    if (!value || typeof value !== 'object' || Array.isArray(value)) return output;
    Object.entries(value).forEach(([id, record]) => {
      if (!byId.has(id) || !record || typeof record !== 'object') return;
      output[id] = {
        status: Object.hasOwn(statuses, record.status) ? record.status : 'todo',
        favorite: record.favorite === true,
        note: typeof record.note === 'string' ? record.note.slice(0, 10000) : '',
        updated: typeof record.updated === 'string' ? record.updated.slice(0, 32) : ''
      };
    });
    return output;
  }

  try {
    records = sanitizeRecords(JSON.parse(localStorage.getItem(storageKey) || '{}'));
  } catch (error) {
    storageAvailable = false;
  }

  function recordFor(id) {
    return records[id] || { status: 'todo', favorite: false, note: '', updated: '' };
  }

  function toast(message) {
    clearTimeout(toastTimer);
    $('toast').textContent = message;
    $('toast').classList.add('is-visible');
    toastTimer = setTimeout(() => $('toast').classList.remove('is-visible'), 2600);
  }

  const storageWarning = '当前为会话模式：记录未写入本机，刷新或关闭页面后会丢失。请通过“导出”保留。';

  function updateStorageNotice(available) {
    storageAvailable = available;
    $('storage-notice').hidden = available;
    $('storage-notice').textContent = available ? '' : storageWarning;
    $('storage-label').textContent = available ? '记录保存在本机' : '会话模式 · 请导出保留';
    document.querySelectorAll('[data-note-storage-hint]').forEach((hint) => {
      hint.textContent = available ? '输入后自动保存在当前浏览器。' : storageWarning;
    });
  }

  function persistRecords() {
    try {
      localStorage.setItem(storageKey, JSON.stringify(records));
      updateStorageNotice(true);
      return true;
    } catch (error) {
      updateStorageNotice(false);
      return false;
    }
  }

  function saveRecord(id, patch) {
    records[id] = { ...recordFor(id), ...patch, updated: new Date().toISOString() };
    const persisted = persistRecords();
    if (!persisted) toast(storageWarning);
    updateProgress();
    return persisted;
  }

  function updateProgress() {
    const mastered = items.filter((item) => recordFor(item.id).status === 'mastered').length;
    $('mastered-count').textContent = mastered;
    $('progress-ring').style.strokeDashoffset = 119.4 * (1 - mastered / items.length);
  }

  function statusSelect(id, className) {
    const select = element('select', className);
    select.setAttribute('aria-label', `${byId.get(id).title}的复习状态`);
    Object.entries(statuses).forEach(([value, text]) => {
      const option = element('option', '', text);
      option.value = value;
      select.append(option);
    });
    select.value = recordFor(id).status;
    select.dataset.status = select.value;
    select.addEventListener('change', () => {
      const persisted = saveRecord(id, { status: select.value });
      select.dataset.status = select.value;
      renderProblems();
      if (readerItem === id) {
        const other = $('reader-content').querySelector('select[data-review-status]');
        if (other) { other.value = select.value; other.dataset.status = select.value; }
      }
      if (persisted) toast(select.value === 'mastered' ? '又掌握了一道题。继续保持。' : `已标记为“${statuses[select.value]}”`);
    });
    return select;
  }

  function favoriteButton(id) {
    const button = element('button', 'acm-star', recordFor(id).favorite ? '★' : '☆');
    button.type = 'button';
    button.setAttribute('aria-label', `${recordFor(id).favorite ? '取消收藏' : '收藏'}：${byId.get(id).title}`);
    button.setAttribute('aria-pressed', String(recordFor(id).favorite));
    button.addEventListener('click', () => {
      saveRecord(id, { favorite: !recordFor(id).favorite });
      renderProblems();
      if (readerItem === id) {
        const current = $('reader-content').querySelector('.acm-star');
        if (current) current.replaceWith(favoriteButton(id));
      }
    });
    return button;
  }

  function syncUrl() {
    const url = new URL(location.href);
    const values = { q: filters.query, category: filters.category, source: filters.source, status: filters.status, saved: filters.favorites ? '1' : '', sort: filters.sort === 'recent' ? '' : filters.sort };
    Object.entries(values).forEach(([key, value]) => value ? url.searchParams.set(key, value) : url.searchParams.delete(key));
    history.replaceState(null, '', url);
  }

  function renderCategories() {
    const fragment = document.createDocumentFragment();
    const categories = ['', ...categoryOrder.filter((category) => items.some((item) => item.category === category))];
    categories.forEach((category) => {
      const button = element('button', 'acm-category');
      button.type = 'button';
      button.setAttribute('aria-pressed', String(category === filters.category));
      button.append(element('span', '', category || '全部题目'), element('small', '', String(category ? items.filter((item) => item.category === category).length : items.length).padStart(2, '0')));
      button.addEventListener('click', () => {
        filters.category = category;
        renderCategories();
        renderProblems();
        syncUrl();
      });
      fragment.append(button);
    });
    $('category-list').replaceChildren(fragment);
  }

  function filteredProblems() {
    const aliases = { dp: '动态规划', dfs: '图与树', bfs: '图与树', math: '数学与数论', graph: '图与树', greedy: '贪心', string: '字符串' };
    const terms = filters.query.trim().toLowerCase().split(/\s+/).filter(Boolean);
    const result = items.filter((item) => {
      const record = recordFor(item.id);
      if (filters.category && item.category !== filters.category) return false;
      if (filters.source && item.group !== filters.source) return false;
      if (filters.favorites && !record.favorite) return false;
      if (filters.status === 'issues' && !item.hasIssues) return false;
      if (filters.status && filters.status !== 'issues' && record.status !== filters.status) return false;
      const haystack = [item.title, item.id, item.category, item.source, item.platform, item.date, item.summary, ...item.tags].join(' ').toLowerCase();
      return terms.every((term) => haystack.includes(term) || (aliases[term] && haystack.includes(aliases[term])));
    });
    if (filters.sort === 'level') result.sort((a, b) => levels[a.level] - levels[b.level] || a.title.localeCompare(b.title, 'zh-CN'));
    if (filters.sort === 'title') result.sort((a, b) => a.title.localeCompare(b.title, 'zh-CN'));
    return result;
  }

  function renderProblems() {
    const visible = filteredProblems();
    const fragment = document.createDocumentFragment();
    visible.forEach((item, index) => {
      const row = element('article', 'acm-problem');
      const number = element('span', 'acm-problem-index', item.number || String(index + 1).padStart(2, '0'));
      number.setAttribute('aria-hidden', 'true');
      const button = element('button', 'acm-problem-main');
      button.type = 'button';
      button.setAttribute('aria-haspopup', 'dialog');
      button.append(element('span', 'acm-problem-title', item.title));
      const meta = element('span', 'acm-problem-meta');
      const level = element('span', 'acm-level', item.level);
      level.dataset.level = item.level;
      meta.append(level, element('span', '', item.source), element('span', '', `${item.versions.length} 份源码${item.statement ? ' · 题面' : ''}`));
      item.tags.slice(0, 2).forEach((tag) => meta.append(element('span', 'acm-problem-tag', tag)));
      if (item.hasIssues) {
        const dot = element('span', 'acm-issue-dot');
        dot.title = '含待补全、错误目录或有明确复盘提醒的原稿';
        dot.setAttribute('aria-label', '含待复盘原稿');
        meta.append(dot);
      }
      button.append(meta);
      button.addEventListener('click', () => openProblem(item.id, button));
      const actions = element('div', 'acm-problem-actions');
      actions.append(favoriteButton(item.id), statusSelect(item.id, 'acm-row-status'));
      row.append(number, button, actions);
      fragment.append(row);
    });
    $('problem-list').replaceChildren(fragment);
    $('results-summary').replaceChildren(element('strong', '', `${visible.length} 道`), document.createTextNode(` / ${items.length} 道题目${filters.category ? ` · ${filters.category}` : ''}`));
    $('empty-state').hidden = visible.length !== 0;
    $('favorites-filter').setAttribute('aria-pressed', String(filters.favorites));
    $('favorites-filter').querySelector('span').textContent = filters.favorites ? '★' : '☆';
  }

  function showReader(trigger) {
    opener = trigger || document.activeElement;
    $('reader').showModal();
    $('reader').scrollTop = 0;
    $('reader-close').focus({ preventScroll: true });
  }

  async function copyCode(code) {
    try {
      if (!navigator.clipboard || !window.isSecureContext) throw new Error('clipboard unavailable');
      await navigator.clipboard.writeText(code);
      toast('代码已复制');
    } catch (error) {
      const area = element('textarea');
      area.value = code;
      area.style.cssText = 'position:fixed;opacity:0;left:0;top:0;';
      ($('reader').open ? $('reader') : document.body).append(area);
      area.select();
      try { toast(document.execCommand('copy') ? '代码已复制' : '请选中代码后复制'); }
      catch (fallbackError) { toast('请选中代码后复制'); }
      area.remove();
    }
  }

  function openProblem(id, trigger) {
    const item = byId.get(id);
    if (!item) return;
    flushNote();
    readerItem = id;
    const content = document.createDocumentFragment();
    const heading = element('div', 'acm-reader-heading');
    const sourceLine = element('div', 'acm-reader-source');
    const level = element('span', 'acm-level', `${item.level} · 复习层级`);
    level.dataset.level = item.level;
    sourceLine.append(level, element('span', '', item.source), element('span', '', item.platform));
    if (item.date) sourceLine.append(element('span', '', item.date));
    const title = element('h2', '', item.title);
    title.id = 'reader-title';
    heading.append(sourceLine, title);
    const tags = element('div', 'acm-reader-tags');
    [item.category, ...item.tags].forEach((text) => tags.append(element('span', '', text)));
    heading.append(tags);
    const actions = element('div', 'acm-reader-actions');
    const status = statusSelect(id, '');
    status.dataset.reviewStatus = '';
    actions.append(status, favoriteButton(id), element('small', '', '复习层级由整理者标注，非平台官方难度'));
    heading.append(actions);
    content.append(heading);

    const layout = element('div', 'acm-reader-layout');
    const notes = element('div', 'acm-reading-notes');
    notes.append(element('h3', '', '从哪里开始想'), element('p', '', item.summary));
    const caution = element('div', 'acm-reading-caution');
    caution.append(element('strong', '', '复盘提醒'), document.createTextNode(item.caution));
    notes.append(caution);
    if (item.statement) {
      const details = element('details');
      details.append(element('summary', '', '展开题目海报'));
      const link = element('a');
      link.href = item.statement;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      link.title = '在新标签页查看完整题面海报';
      const img = element('img');
      img.src = item.statement;
      img.alt = `${item.title}的题目海报`;
      img.loading = 'lazy';
      img.decoding = 'async';
      link.append(img);
      details.append(link, element('small', '', '题目海报来自个人题档；点击图片可放大查看。'));
      notes.append(details);
    }
    if (item.editorial) {
      const details = element('details');
      details.append(element('summary', '', '展开参考注释与推导'), element('pre', 'acm-editorial-text', item.editorial), element('small', '', item.editorialSource));
      notes.append(details);
    }
    if (item.links.length) {
      const links = element('div', 'acm-reading-links');
      item.links.forEach(({ label, url }) => {
        const link = element('a', '', `${label} ↗`);
        link.href = url;
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
        links.append(link);
      });
      notes.append(links);
    }
    const personal = element('div', 'acm-personal-note');
    const label = element('label', '', '留给下一次的笔记');
    label.htmlFor = 'personal-note';
    const textarea = element('textarea');
    textarea.id = 'personal-note';
    textarea.maxLength = 10000;
    textarea.placeholder = '这道题卡在哪里？哪个边界容易忘？';
    textarea.value = recordFor(id).note;
    textarea.addEventListener('input', () => {
      clearTimeout(noteTimer);
      notePending = { id, value: textarea.value };
      noteTimer = setTimeout(flushNote, 400);
    });
    const storageHint = element('small', '', storageAvailable ? '输入后自动保存在当前浏览器。' : storageWarning);
    storageHint.dataset.noteStorageHint = '';
    personal.append(label, textarea, storageHint);
    notes.append(personal);
    const codePanel = element('div', 'acm-source-panel');
    const tools = element('div', 'acm-source-tools');
    const versions = element('select');
    versions.setAttribute('aria-label', '选择源码版本');
    item.versions.forEach((version, index) => {
      const duplicateName = item.versions.some((other, otherIndex) => otherIndex !== index && other.name === version.name && other.language === version.language);
      const filename = version.path.split('/').pop();
      const phase = version.path.includes('/upsolve/') ? '补题' : item.group === 'icpc' ? '赛时' : '原存档';
      const suffix = duplicateName ? ` · ${phase} / ${filename}` : '';
      const option = element('option', '', `${version.name} · ${version.language}${suffix}`);
      option.value = index;
      versions.append(option);
    });
    const copy = element('button', 'acm-copy', '复制代码');
    copy.type = 'button';
    copy.addEventListener('click', () => copyCode(item.versions[Number(versions.value)].code));
    tools.append(versions, copy);
    const path = element('p', 'acm-source-path');
    const notice = element('div', 'acm-version-notice');
    const pre = element('pre', 'acm-source-code');
    const code = element('code');
    pre.append(code);
    function renderVersion() {
      const version = item.versions[Number(versions.value)];
      path.textContent = `题档 / ${version.path}`;
      // Never interpolate learning source into HTML: C++ angle brackets stay text.
      code.textContent = version.code || '// 这份文件为空，等下一次把思路补上。';
      const messages = {
        empty: '原文件为空，暂不能作为可运行解法。',
        incomplete: '这份原稿缺少入口或完整输出逻辑，适合补全练习。',
        error: '来自 ERROR 目录，保留作错误分析。请对照其他版本复盘。',
        'ac-directory': '来自原题档的 AC 目录；本页未重新提交判题。',
        reference: 'AI 参考版本，保留原注释；请结合题面独立验证。',
        original: '个人原稿。复盘提醒与源码一起阅读；本页未重新提交判题。'
      };
      notice.textContent = messages[version.status];
      pre.scrollTop = 0;
      pre.scrollLeft = 0;
    }
    versions.addEventListener('change', renderVersion);
    codePanel.append(tools, path, notice, pre);
    renderVersion();
    layout.append(notes, codePanel);
    content.append(layout);
    $('reader-content').replaceChildren(content);
    $('reader-breadcrumb').textContent = `ACM NOTEBOOK / ${item.source}`;
    showReader(trigger);
  }

  function flushNote() {
    clearTimeout(noteTimer);
    if (!notePending) return;
    const pending = notePending;
    notePending = null;
    saveRecord(pending.id, { note: pending.value });
  }

  const templates = [
    {
      title: '快速幂与模逆元', label: 'NUMBER THEORY', description: '把线性乘法压成对指数的二进制枚举。',
      guide: '适用于整数幂取模。费马小定理求逆元要求 mod 为质数，且 a 与 mod 互质；通用大模数还需处理乘法溢出。整理自「小红的陡峭值（五）」与「杨辉三角」。',
      code: `using ll = long long;
ll qpow(ll a, ll b, ll mod) {
    a = (a % mod + mod) % mod;
    ll result = 1 % mod;
    while (b > 0) {
        if (b & 1) result = result * a % mod;
        a = a * a % mod;
        b >>= 1;
    }
    return result;
}
// mod 为质数且 gcd(a, mod) == 1 时：
// inverse(a) = qpow(a, mod - 2, mod)
// 时间 O(log b)，额外空间 O(1)。`
    },
    {
      title: 'BFS 与树直径', label: 'GRAPH & TREE', description: '从无权最短路，到树上最远点。',
      guide: 'BFS 首次访问即得到无权最短距离。在连通树上，从任意点找到最远点 A，再从 A 找到最远点 B，得到一条直径；每个点的最远距离为 max(distA, distB)。整理自「小绿的房子」。',
      code: `vector<int> bfs(const vector<vector<int>>& g, int start) {
    vector<int> dist(g.size(), -1);
    queue<int> q;
    dist[start] = 0;
    q.push(start);
    while (!q.empty()) {
        int u = q.front(); q.pop();
        for (int v : g[u]) {
            if (dist[v] != -1) continue;
            dist[v] = dist[u] + 1;
            q.push(v);
        }
    }
    return dist;
}
// 选最远点时只在合法节点编号中枚举。
// 树直径性质不能直接套用到一般图。
// 时间 O(V + E)，空间 O(V)。`
    },
    {
      title: '树状数组 · 差分', label: 'DATA STRUCTURE', description: '区间增量，转换成两次端点修改。',
      guide: '为「区间增量与单点求值」整理的优化模板。原数组单独保留，树状数组维护增量的差分：区间 [l,r] 加 x 等价于 d[l]+=x、d[r+1]−=x，单点值为 a[i]+prefix(i)。下标从 1 开始。',
      code: `struct Fenwick {
    int n;
    vector<long long> bit;
    explicit Fenwick(int n) : n(n), bit(n + 1, 0) {}
    void add(int i, long long delta) {
        for (; i <= n; i += i & -i) bit[i] += delta;
    }
    long long prefix(int i) const {
        long long sum = 0;
        for (; i > 0; i -= i & -i) sum += bit[i];
        return sum;
    }
    void rangeAdd(int l, int r, long long x) {
        add(l, x);
        if (r < n) add(r + 1, -x);
    }
};
// query(i) = original[i] + tree.prefix(i)
// 禁止 add(0, x)，否则 lowbit(0)==0 导致死循环。
// 单次修改/查询 O(log n)，空间 O(n)。`
    },
    {
      title: '二分 · 第一个可行值', label: 'BINARY SEARCH', description: '先写出单调性，再决定左右边界。',
      guide: '在闭区间 [lo,hi] 中求第一个 check(x) 为真的值，要求 false…false、true…true，且 hi 已保证可行。用于「阶乘」中按质因子指数二分最小 n。',
      code: `long long firstTrue(long long lo, long long hi,
                    const function<bool(long long)>& check) {
    while (lo < hi) {
        long long mid = lo + (hi - lo) / 2;
        if (check(mid)) hi = mid;
        else lo = mid + 1;
    }
    return lo;
}
long long exponentInFactorial(long long n, long long p) {
    long long total = 0;
    while (n) {
        n /= p;
        total += n;
    }
    return total;
}
// p 为质数，check(n) = exponentInFactorial(n,p) >= need。
// 二分 O(log(hi-lo)) 次，每次 check 另计。`
    },
    {
      title: '中位数窗口代价', label: 'TWO POINTERS', description: '把绝对值之和拆成左右两段前缀和。',
      guide: '数组 a 已升序，pre 为前缀和，下标从 1 开始。将窗口 [l,r] 统一成某个值时，中位数使绝对偏差最小；可与滑动窗口配合。整理自「加减」。',
      code: `// a[1..n] 已排序；pre[0] = 0。
for (int i = 1; i <= n; ++i)
    pre[i] = pre[i - 1] + a[i];

auto cost = [&](int l, int r) -> long long {
    int mid = l + (r - l) / 2;
    long long left = a[mid] * (mid - l)
                   - (pre[mid - 1] - pre[l - 1]);
    long long right = (pre[r] - pre[mid])
                    - a[mid] * (r - mid);
    return left + right;
};
int answer = 0;
for (int l = 1, r = 1; r <= n; ++r) {
    while (l < r && cost(l, r) > budget) ++l;
    answer = max(answer, r - l + 1);
}
// budget >= 0；排序 O(n log n)，扫描 O(n)。`
    },
    {
      title: 'KMP · 前缀函数', label: 'STRING', description: '在失配时，复用已经确认的前后缀。',
      guide: 'pi[i] 表示 s[0..i] 的最长相等真前后缀长度。失配时 j=pi[j−1] 回退，既保留有效信息，又避免重扫。整理自「子串匹配」；完整匹配时同样使用这个回退规则。',
      code: `vector<int> prefixFunction(const string& s) {
    vector<int> pi(s.size(), 0);
    for (int i = 1; i < (int)s.size(); ++i) {
        int j = pi[i - 1];
        while (j > 0 && s[i] != s[j])
            j = pi[j - 1];
        if (s[i] == s[j]) ++j;
        pi[i] = j;
    }
    return pi;
}
// 扫描文本时，j 记录已匹配的模式长度。
// j == pattern.size() 时记录起点，然后 j = pi[j-1]。
// 这样能保留重叠匹配，例如 aaa 中的 aa。
// 前缀函数 O(m)，扫描文本 O(n)。`
    },
    {
      title: '整除分块', label: 'NUMBER THEORY', description: '让相同商的整个区间，只算一次。',
      guide: '对于正整数 l，令 q=floor(k/l)，则相同商的最右端是 floor(k/q)。整理自「余数求和」。下面模板用 __int128 保护区间和的中间乘法，适用于支持该扩展的编译器。',
      code: `// 求 sum(i=1..n) (k % i)，n,k >= 0。
__int128 remainderSum(long long n, long long k) {
    __int128 answer = (__int128)n * k;
    for (long long l = 1, r; l <= n; l = r + 1) {
        long long q = k / l;
        if (q == 0) break;
        r = min(n, k / q);
        __int128 intervalSum = ((__int128)l + r)
                             * (r - l + 1) / 2;
        answer -= intervalSum * q;
    }
    return answer;
}
// 块数 O(sqrt(k))，额外空间 O(1)。
// 输出 __int128 时另写十进制转换函数。`
    },
    {
      title: 'Tarjan · 强连通分量', label: 'DIRECTED GRAPH', description: '通过 dfn 与 low 找到有向图中的环。',
      guide: '整理自「核心信任者」，将原稿的栈内边更新改为标准 dfn[v] 写法。dfn 是首次访问时间，low 表示能到达的最小时间戳。递归版本需要注意长链栈深。',
      code: `// g,dfn,low,component,inStack,st 已按 n 初始化。
// timer = components = 0，dfn 初值 0。
void tarjan(int u) {
    dfn[u] = low[u] = ++timer;
    st.push(u);
    inStack[u] = true;
    for (int v : g[u]) {
        if (!dfn[v]) {
            tarjan(v);
            low[u] = min(low[u], low[v]);
        } else if (inStack[v]) {
            low[u] = min(low[u], dfn[v]);
        }
    }
    if (dfn[u] == low[u]) {
        ++components;
        while (true) {
            int v = st.top(); st.pop();
            inStack[v] = false;
            component[v] = components;
            if (v == u) break;
        }
    }
}
// 对每个未访问节点调用 tarjan，时间 O(V+E)。`
    }
  ];

  function renderTemplates() {
    const fragment = document.createDocumentFragment();
    templates.forEach((template, index) => {
      const button = element('button', 'acm-template-card');
      button.type = 'button';
      button.setAttribute('aria-haspopup', 'dialog');
      button.append(element('span', '', `${String(index + 1).padStart(2, '0')} / ${template.label}`), element('strong', '', template.title), element('p', '', template.description), element('span', '', '打开模板 ↗'));
      button.addEventListener('click', () => {
        flushNote();
        readerItem = null;
        const wrapper = element('div', 'acm-template-reader');
        const title = element('h2', '', template.title);
        title.id = 'reader-title';
        const copy = element('button', 'acm-copy', '复制模板');
        copy.type = 'button';
        copy.addEventListener('click', () => copyCode(template.code));
        const pre = element('pre');
        pre.append(element('code', '', template.code));
        wrapper.append(element('p', 'acm-kicker', template.label), title, element('p', '', template.guide), copy, pre);
        $('reader-content').replaceChildren(wrapper);
        $('reader-breadcrumb').textContent = 'ACM NOTEBOOK / TEMPLATE';
        showReader(button);
      });
      fragment.append(button);
    });
    $('template-list').replaceChildren(fragment);
  }

  function bindFilters() {
    const validCategories = new Set(categoryOrder);
    if (!validCategories.has(filters.category)) filters.category = '';
    if (![...$('source-filter').options].some((option) => option.value === filters.source)) filters.source = '';
    if (![...$('status-filter').options].some((option) => option.value === filters.status)) filters.status = '';
    if (![...$('sort-order').options].some((option) => option.value === filters.sort)) filters.sort = 'recent';
    $('search').value = filters.query;
    $('source-filter').value = filters.source;
    $('status-filter').value = filters.status;
    $('sort-order').value = filters.sort;
    $('search').addEventListener('input', () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => { filters.query = $('search').value; renderProblems(); syncUrl(); }, 120);
    });
    [['source-filter', 'source'], ['status-filter', 'status'], ['sort-order', 'sort']].forEach(([id, key]) => {
      $(id).addEventListener('change', () => { filters[key] = $(id).value; renderProblems(); syncUrl(); });
    });
    $('favorites-filter').addEventListener('click', () => { filters.favorites = !filters.favorites; renderProblems(); syncUrl(); });
    $('clear-filters').addEventListener('click', () => {
      Object.assign(filters, { query: '', category: '', source: '', status: '', favorites: false, sort: 'recent' });
      $('search').value = '';
      $('source-filter').value = '';
      $('status-filter').value = '';
      $('sort-order').value = 'recent';
      renderCategories(); renderProblems(); syncUrl();
    });
  }

  $('reader-close').addEventListener('click', () => $('reader').close());
  $('reader').addEventListener('close', () => {
    flushNote();
    readerItem = null;
    if (opener && opener.isConnected) opener.focus({ preventScroll: true });
  });
  $('reader').addEventListener('click', (event) => {
    if (event.target !== $('reader')) return;
    const rect = $('reader').getBoundingClientRect();
    if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) $('reader').close();
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === '/' && !event.ctrlKey && !event.metaKey && !$('reader').open && !['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName)) {
      event.preventDefault();
      $('search').focus();
      $('search').scrollIntoView({ block: 'center' });
    }
  });
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden') flushNote(); });
  window.addEventListener('pagehide', flushNote);
  window.addEventListener('storage', (event) => {
    if (event.key !== storageKey) return;
    try { records = sanitizeRecords(JSON.parse(event.newValue || '{}')); updateProgress(); renderProblems(); }
    catch (error) { /* Keep the current tab's usable records if another tab writes invalid data. */ }
  });
  $('export-progress').addEventListener('click', () => {
    flushNote();
    const data = { format: 'hyper-acm-review', version: 1, exportedAt: new Date().toISOString(), records };
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = element('a');
    link.href = url;
    link.download = `hyper-acm-review-${new Date().toISOString().slice(0, 10)}.json`;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    toast('复习记录已导出');
  });
  $('import-progress').addEventListener('change', async (event) => {
    const file = event.target.files[0];
    if (!file) return;
    try {
      if (file.size > 3000000) throw new Error('too large');
      const data = JSON.parse(await file.text());
      if (data.format !== 'hyper-acm-review' || data.version !== 1 || !data.records || typeof data.records !== 'object') throw new Error('format');
      const incoming = sanitizeRecords(data.records);
      Object.entries(incoming).forEach(([id, record]) => {
        const current = recordFor(id);
        if (!records[id] || !current.updated || record.updated >= current.updated) records[id] = record;
      });
      const persisted = persistRecords();
      updateProgress(); renderProblems();
      toast(persisted ? `已合并 ${Object.keys(incoming).length} 道题的复习记录` : `已在本次会话合并 ${Object.keys(incoming).length} 道题；刷新后会丢失，请导出保留。`);
    } catch (error) {
      toast('无法导入，请选择此页面导出的有效复习记录 JSON。');
    }
    event.target.value = '';
  });
  $('total-problems').textContent = library.counts.problems;
  $('total-versions').textContent = library.counts.versions;
  $('total-categories').textContent = library.counts.categories;
  updateStorageNotice(storageAvailable);
  bindFilters();
  renderCategories();
  renderProblems();
  renderTemplates();
  updateProgress();
})();
