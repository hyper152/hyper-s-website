(() => {
  'use strict';
  const notes = [
    { id: 'logic', subject: 'discrete', chapter: '01', title: '命题逻辑', tags: '真值表 蕴涵 等价 德摩根 范式 重言式', intro: '把自然语言翻译为命题，再用真值表或等值式检验推理。先记住联结词的语义。', formula: 'P → Q ≡ ¬P ∨ Q<br>¬(P ∧ Q) ≡ ¬P ∨ ¬Q', points: ['<strong>蕴涵：</strong>仅在 P 真、Q 假时，P → Q 为假；逆命题不能直接替换原命题。', '<strong>等价：</strong>P → Q 与 ¬Q → ¬P 等价。含 n 个命题变元的真值表有 2<sup>n</sup> 行。', '<strong>主范式：</strong>主析取范式汇集使命题为真的极小项；主合取范式汇集使命题为假的极大项。'], question: '自查：怎样否定「如果 P，那么 Q」？', answer: '<p>否定的是整个蕴涵式：¬(P → Q) ≡ P ∧ ¬Q。只把 Q 取反仍写成 P → ¬Q，并不等价。</p><p>可从唯一反例理解：条件 P 已发生，但结论 Q 没发生。</p>', source: '笔记 01 · 命题逻辑' },
    { id: 'predicate', subject: 'discrete', chapter: '02', title: '谓词逻辑', tags: '全称 存在 量词 前束范式 作用域', intro: '量词决定讨论对象的范围与依赖关系。交换量词前，先判断“同一个”对象能否适用于所有情况。', formula: '¬∀x P(x) ≡ ∃x ¬P(x)<br>¬∃x P(x) ≡ ∀x ¬P(x)', points: ['<strong>否定：</strong>量词翻转，谓词取反；多个量词要逐层处理。', '<strong>依赖：</strong>∀x∃y P(x,y) 中 y 可随 x 变化；∃y∀x P(x,y) 要求一个固定 y。', '<strong>前束范式：</strong>先消去蕴涵，推动否定内移，再重命名约束变元，避免自由变元被意外约束。'], question: '自查：∀x∃y (y > x) 与 ∃y∀x (y > x) 相同吗？', answer: '<p>在实数域中，前者为真：每个 x 都能选 y=x+1。后者为假：不存在大于所有实数的固定实数 y。</p><p>结论依赖论域；写证明时应先说明论域。</p>', source: '笔记 01 · 谓词逻辑' },
    { id: 'sets', subject: 'discrete', chapter: '03', title: '集合论', tags: '集合 包含 排斥 笛卡尔积 幂集 德摩根', intro: '先分清元素与子集，再用运算恒等式、包含排斥原理处理计数。', formula: '|A ∪ B| = |A| + |B| − |A ∩ B|<br>|𝒫(A)| = 2<sup>|A|</sup>', points: ['<strong>元素与集合：</strong>a ∈ A 表示元素归属，B ⊆ A 表示包含；∅ ⊆ A 对任意集合成立。', '<strong>补集：</strong>相对于给定全集 U，(A ∪ B)<sup>c</sup> = A<sup>c</sup> ∩ B<sup>c</sup>。', '<strong>笛卡尔积：</strong>A × B 由有序对组成；有限集合满足 |A × B| = |A|·|B|。'], question: '自查：三个集合并集怎样计数？', answer: '<div class="math-card-formula">|A ∪ B ∪ C| = |A| + |B| + |C|<br>− |A ∩ B| − |A ∩ C| − |B ∩ C|<br>+ |A ∩ B ∩ C|</div><p>三重交中的元素被加入 3 次、减去 3 次，最后需再加 1 次。</p>', source: '笔记 01 · 集合论' },
    { id: 'relations', subject: 'discrete', chapter: '04', title: '关系与偏序', tags: '关系 自反 对称 反对称 传递 闭包 等价 偏序 哈斯图', intro: '把性质逐个核对，比只凭关系的名字判断可靠。等价关系负责分类，偏序关系负责比较。', formula: '等价关系 = 自反 + 对称 + 传递<br>偏序关系 = 自反 + 反对称 + 传递', points: ['<strong>等价类：</strong>等价关系与集合的划分相对应，不同等价类互不相交。', '<strong>反对称：</strong>xRy 且 yRx 蕴含 x=y；它与“不是对称”不是同一个条件。', '<strong>哈斯图：</strong>省略自环和传递边，通常把较大元素画在上方；极大元不一定是最大元。'], question: '自查：{1,2,3,6} 上的整除关系是什么关系？', answer: '<p>整除关系自反、反对称且传递，因此构成偏序。1 是最小元，6 是最大元；2 与 3 不可比较。</p><p>哈斯图保留 1—2、1—3、2—6、3—6，省去传递得到的 1—6。</p>', source: '笔记 01 · 关系' },
    { id: 'algebra', subject: 'discrete', chapter: '05', title: '代数结构与循环群', tags: '半群 群 环 域 子群 陪集 拉格朗日 生成元 循环群 布尔代数', intro: '从封闭性、结合律、单位元、逆元逐层识别结构；求循环群子群时，让阶数带路。', formula: 'ord([k]) = n / gcd(k,n)<br>H<sub>d</sub> = ⟨[n/d]⟩，d | n', points: ['<strong>群：</strong>运算封闭、满足结合律、存在单位元且每个元素有逆元；交换律另构成阿贝尔群。', '<strong>拉格朗日：</strong>有限群的子群阶整除群阶；一般群里“整除”不能保证对应阶子群存在。', '<strong>循环群：</strong>在加法群 ℤ<sub>n</sub> 中，每个正因数 d 对应唯一 d 阶子群；生成元为 [n/d]。'], question: '自查：ℤ₈ 的 4 阶子群及其陪集？', answer: '<p>8/4=2，所以 H=⟨[2]⟩={0,2,4,6}。元素 [2] 的阶为 8/gcd(2,8)=4。</p><p>奇数的陪集均为 [1]+H={1,3,5,7}；偶数的陪集为 H。注意 [6] 也生成同一个子群。</p>', source: '笔记 01 · 代数结构 / 循环群方法笔记' },
    { id: 'graphs', subject: 'discrete', chapter: '06', title: '图论基础', tags: '图论 度 握手定理 连通 邻接矩阵 最短路 Dijkstra', intro: '先确定有向或无向、是否有重边和自环，再读矩阵与度数，避免把不同约定混用。', formula: '无向图：Σ deg(v) = 2|E|<br>有向图：Σ deg⁺(v) = Σ deg⁻(v) = |E|', points: ['<strong>握手定理：</strong>无向图的奇度顶点数必为偶数；自环对无向度贡献 2。', '<strong>邻接矩阵：</strong>A<sup>k</sup> 的 (i,j) 元统计长度 k 的游走数，游走可重复顶点和边。', '<strong>最短路：</strong>Dijkstra 要求非负边权；有负权时不能直接沿用其贪心正确性。'], question: '自查：简单无向图的度序列 3,3,3,2 可能吗？', answer: '<p>不可能。总度数 3+3+3+2=11 为奇数，违反 Σdeg(v)=2|E|。</p><p>总度为偶数只是必要条件；通过此检查仍不能直接断言任意度序列可实现。</p>', source: '笔记 01 · 图论基础' },
    { id: 'special-graphs', subject: 'discrete', chapter: '07', title: '特殊图与树', tags: '欧拉 哈密顿 树 最小生成树 平面图 二部图 Hall 匹配 Huffman', intro: '欧拉问题围绕边，哈密顿问题围绕顶点；树、平面图与二部图各有一组好用的结构约束。', formula: '树：|E| = |V| − 1<br>连通平面图：|V| − |E| + |F| = 2', points: ['<strong>欧拉：</strong>无向图所有非零度顶点连通时，0 个奇度顶点有欧拉回路，2 个有非闭合欧拉通路。', '<strong>树与生成树：</strong>树连通无环；Kruskal 按边权避圈，Prim 从已选顶点向外扩展，均用于无向带权图。', '<strong>二部图：</strong>无奇环 ⇔ 可二染色；Hall 条件 |N(S)|≥|S|（对左部每个 S）判定能覆盖左部的匹配。'], question: '自查：简单连通平面图为什么有 m ≤ 3n−6？', answer: '<p>对 n≥3 的简单连通平面图，每个面的边界长度至少 3，且所有面边界长度之和为 2m，得 3f≤2m。</p><p>代入 n−m+f=2，得到 m≤3n−6。使用结论前须核对“简单、连通、平面、n≥3”。</p>', source: '笔记 01 · 特殊图' },
    { id: 'combinatorics', subject: 'discrete', chapter: '08', title: '组合数学', tags: '排列 组合 二项式 生成函数 递推 特征方程 容斥', intro: '先判断是否计顺序、是否允许重复，再选计数模型。递推问题要把初始条件与递推式一同写下。', formula: 'C(n,r) = n! / [r!(n−r)!]<br>(1−x)<sup>−k</sup> = Σ<sub>n≥0</sub> C(n+k−1,k−1)x<sup>n</sup>', points: ['<strong>有序选择：</strong>不重复排列 P(n,r)=n!/(n−r)!；允许重复的长度 r 序列共有 n<sup>r</sup> 个。', '<strong>可重复组合：</strong>从 n 类取 r 个且不计顺序，数量为 C(n+r−1,r)。', '<strong>线性递推：</strong>a<sub>n</sub>=p a<sub>n−1</sub>+q a<sub>n−2</sub> 对应特征方程 λ²−pλ−q=0，再用初值确定常数。'], question: '自查：x₁+x₂+x₃=5 有多少组非负整数解？', answer: '<p>把 5 个相同元素放入 3 类，使用隔板法：C(5+3−1,3−1)=C(7,2)=21。</p><p>若要求三个变量都为正，先令 yᵢ=xᵢ−1，转化为总和 2 的非负解，结果为 C(4,2)=6。</p>', source: '笔记 01 · 组合数学' },
    { id: 'residual', subject: 'numerical', chapter: '01', title: '误差、残差与病态性', tags: '线性方程组 误差 残差 范数 条件数 病态 cond', intro: '算得很“稳”的残差，不一定意味着近似解很准确。先分清你正在衡量的是方程满足程度还是解的偏差。', formula: 'r = b − A x̂<br>κ(A) = ‖A‖ · ‖A<sup>−1</sup>‖', points: ['<strong>相对残差：</strong>‖b−Ax̂‖/‖b‖；b=0 时需改用绝对残差或另设尺度。', '<strong>相对误差：</strong>‖x̂−x‖/‖x‖；真实解未知时不能直接计算。实验中可借已知 x 进行比较。', '<strong>条件数：</strong>对可逆 A，在一致范数下有相对误差 ≤ κ(A)·相对残差；病态矩阵会放大误差。'], question: '自查：相对残差达到 10⁻⁸，就有 8 位准确数字吗？', answer: '<p>不能这样推断。若 κ(A) 很大，上界可能仍很宽；例如 κ(A)=10⁸ 时，10⁻⁸ 的相对残差给出的相对误差上界是 1。</p><p>笔记实验把正常数据与病态数据分别测试，比较残差和已知真实误差。</p>', source: '笔记 03 · 线性方程组实验' },
    { id: 'lu', subject: 'numerical', chapter: '02', title: 'LU 分解与直接法', tags: 'LU 分解 高斯 消元 前代 回代 主元 直接法', intro: '把一次方程组求解拆成分解、前代、回代；同一矩阵对应多个右端项时，可以复用分解结果。', formula: 'A = LU → Ly = b → Ux = y<br>选主元时常写 PA = LU', points: ['<strong>前代：</strong>下三角系统从第一行起求；回代则从上三角系统的最后一行向前求。', '<strong>主元：</strong>课堂无换行实现要求消元过程中主元非零；一般问题应考虑选主元，控制数值误差。', '<strong>复用：</strong>稠密分解通常 O(n³)，每个新右端项的两次三角求解约 O(n²)。'], question: '自查：A 可逆就保证无换行 LU 消元能运行吗？', answer: '<p>不能。例如 A=[[0,1],[1,1]] 可逆，但首个主元为零，无换行消元会失败。交换两行后才可继续。</p><p>实验中的基础 LU 明确检测零主元；其适用前提不能推广到任意可逆矩阵。</p>', source: '笔记 03 · 自编 LU 与 NumPy 对照' },
    { id: 'jacobi', subject: 'numerical', chapter: '03', title: 'Jacobi 迭代', tags: 'Jacobi 雅可比 线性方程组 迭代矩阵 谱半径 对角占优', intro: '本轮每个分量都使用上一轮的完整向量。实现时先整体算出新值，避免不小心写成另一种迭代。', formula: 'A = D + L + U<br>x<sup>(k+1)</sup> = D<sup>−1</sup>[b − (L+U)x<sup>(k)</sup>]', points: ['<strong>条件：</strong>对角元素不能为零；迭代矩阵 B<sub>J</sub>=−D<sup>−1</sup>(L+U)。', '<strong>收敛：</strong>对任意初值收敛的充要条件是 ρ(B<sub>J</sub>)<1；严格行对角占优是一个充分条件。', '<strong>终止：</strong>同时设置残差阈值、迭代上限和非有限值检测；迭代结束本身不说明已收敛。'], question: '自查：原地逐个覆盖 xᵢ 还是 Jacobi 吗？', answer: '<p>若右侧读取了本轮刚更新的分量，就改变了 Jacobi 的“全旧值”规则。Gauss–Seidel 使用这样的新旧值混合，而 Jacobi 要保留完整 old 向量。</p><p>对称正定并不单独保证 Jacobi 收敛，仍要检查其迭代条件。</p>', source: '笔记 03 · Jacobi 收敛实验' },
    { id: 'sor', subject: 'numerical', chapter: '04', title: 'Gauss–Seidel 与 SOR', tags: 'Gauss Seidel 高斯 赛德尔 SOR 超松弛 omega 迭代', intro: '按分量更新，左侧已经计算的部分用新值，右侧尚未计算的部分用旧值；再用松弛因子调节步长。', formula: 'tᵢ = [bᵢ − Σ<sub>j&lt;i</sub>aᵢⱼxⱼ<sup>新</sup> − Σ<sub>j&gt;i</sub>aᵢⱼxⱼ<sup>旧</sup>] / aᵢᵢ<br>xᵢ<sup>新</sup> = (1−ω)xᵢ<sup>旧</sup> + ωtᵢ', points: ['<strong>ω=1：</strong>退化为 Gauss–Seidel。0<ω<1 为欠松弛，1<ω<2 为超松弛。', '<strong>收敛前提：</strong>A 对称正定且 0<ω<2 时，SOR 收敛；一般矩阵不能只凭 ω 的区间保证。', '<strong>调参：</strong>比较实际迭代次数和残差；更大的 ω 不保证更快，越接近 2 也未必越好。'], question: '自查：为什么要写 old=x.copy()？', answer: '<p>在 NumPy 中 old=x 会让两个名字引用同一个数组，原地修改 x 也改变了“旧值”。copy() 才能保留本轮开始前的完整向量。</p><p>实验扫描松弛因子时，应统一初值、误差尺度与停止准则。</p>', source: '笔记 03 · SOR 松弛因子对照' },
    { id: 'fixed-point', subject: 'numerical', chapter: '05', title: '不动点与收敛阶', tags: '不动点 压缩映像 迭代收敛 导数 线性收敛 二阶 phi', intro: '先证明迭代确实趋向目标根，再讨论它有多快。局部导数和整个区间上的收敛保证承担不同任务。', formula: 'φ(I) ⊆ I，max<sub>x∈I</sub>|φ′(x)| ≤ q < 1<br>|e<sub>n+1</sub>| / |e<sub>n</sub>|<sup>p</sup> → C，0 < C < ∞', points: ['<strong>压缩映像：</strong>闭区间内的自映射加一致压缩，保证唯一不动点及从区间内初值的收敛。', '<strong>局部阶数：</strong>φ′(α)≠0 且其绝对值小于 1 时通常为一阶；前 p−1 阶导数为零、第 p 阶非零时为 p 阶。', '<strong>易错：</strong>某个大区间上 max|φ′|≥1 只说明该压缩判据不适用，不能直接推出发散。'], question: '自查：xₙ₊₁=1+1/xₙ²，x₀=1.5，怎样证明收敛？', answer: '<p>对 f(x)=x³−x²−1，目标根 α≈1.4655712319。选 I=[√2,1.5]，可以验证 φ(I)⊆I，且 max|φ′|≤1/√2<1。</p><p>所以该初值的迭代收敛。根处 φ′(α)=−2/α³≠0，因此为一阶收敛。</p>', source: '笔记 02 · 第 1 题' },
    { id: 'bisection', subject: 'numerical', chapter: '06', title: '二分法', tags: '二分法 隔根 连续 误差估计 根 区间', intro: '保留一个始终包含根的异号区间。它的优势是误差界明确，代价是收敛速度较慢。', formula: 'f 连续，f(a)f(b) < 0<br>n 次折半后：区间长 = (b−a)/2<sup>n</sup>', points: ['<strong>保留异号：</strong>取中点 c=(a+b)/2，根据 f(c) 的符号保留仍异号的半区间；f(c)=0 时直接停止。', '<strong>误差：</strong>取当前区间中点为近似根时，误差不超过当前区间长度的一半。', '<strong>限制：</strong>异号区间保证至少一个根，未必唯一；偶重根两侧可能同号，不能靠此判据发现。'], question: '自查：初始区间长 1，怎样让中点误差 ≤10⁻³？', answer: '<p>n 次区间折半后，中点误差 ≤1/2ⁿ⁺¹。要求 2ⁿ⁺¹≥1000，可取 n=9，此时误差上界为 1/1024。</p><p>注意数的是“折半次数”；若按函数求值次数计数，约定需要另外说明。</p>', source: '笔记 02 · 第 3 题' },
    { id: 'newton', subject: 'numerical', chapter: '07', title: '牛顿法', tags: '牛顿 Newton 导数 切线 二阶 重根 初值', intro: '用当前点的切线近似函数，迭代寻找横轴交点。速度依赖根的性质，也依赖初值是否足够合适。', formula: 'x<sub>n+1</sub> = x<sub>n</sub> − f(x<sub>n</sub>)/f′(x<sub>n</sub>)', points: ['<strong>局部二阶：</strong>函数足够光滑、α 为单根且初值足够近时，通常二阶收敛。', '<strong>风险：</strong>导数接近零可能产生很大步长；越出定义域、震荡或发散都需检测。', '<strong>根的顺序：</strong>求“最小正根”应先分析函数和隔根区间，再从合适初值启动迭代。'], question: '自查：二阶收敛是否说明任意初值都收敛？', answer: '<p>不说明。二阶是局部收敛速度结论，前提包含初值进入合适的邻域。例如 f(x)=x³−2x+2，从 x₀=0 开始会在 0 与 1 之间循环。</p><p>实际求根可先使用保区间方法，再在条件合适时切换牛顿步。</p>', source: '笔记 02 · 第 3 题' },
    { id: 'relaxation', subject: 'numerical', chapter: '08', title: '松弛加速：从迭代到牛顿', tags: '松弛 加速 动态 参数 牛顿 不动点 二阶', intro: '加权更新可以改变根处导数。动态松弛因子的一种选择，恰好得到残差函数的牛顿法。', formula: 'ωₙ = 1 / [1−φ′(xₙ)]<br>x<sub>n+1</sub> = (1−ωₙ)xₙ + ωₙφ(xₙ)', points: ['<strong>等价变换：</strong>令 G(x)=x−φ(x)，上式等于 x<sub>n+1</sub>=xₙ−G(xₙ)/G′(xₙ)。', '<strong>例题：</strong>φ(x)=1+x<sup>−2</sup> 时，化简得到 x<sub>n+1</sub>=(xₙ³+3xₙ)/(xₙ³+2)。', '<strong>条件：</strong>分母必须非零；“消去一阶项”之后，仍要核对定义域、实际收敛与高阶导数条件。'], question: '自查：原笔记中 x₀=1.5 的加速效果如何？', answer: '<p>原解析给出的迭代为：1.5 → 1.4651162791 → 1.4655711495 → 1.4655712319。</p><p>解析先证明从第一步起序列有界单调趋向 α，再验证 Ψ′(α)=0、Ψ″(α)≠0，得二阶收敛；这比只比较几次小数更充分。</p>', source: '笔记 02 · 第 1 题加速分析' }
  ];

  const cards = document.getElementById('math-cards');
  const search = document.getElementById('math-search');
  const reviewOnly = document.getElementById('math-review-only');
  const count = document.getElementById('math-result-count');
  const empty = document.getElementById('math-empty');
  const expand = document.getElementById('math-expand');
  const storageKey = 'hyper-math-toolkit-reviewed-v1';
  let reviewed = new Set();
  let subject = 'all';
  let storageAvailable = true;
  try {
    const stored = JSON.parse(localStorage.getItem(storageKey) || '[]');
    if (Array.isArray(stored)) reviewed = new Set(stored.filter(id => notes.some(note => note.id === id)));
  } catch (_) { storageAvailable = false; }

  function updateStorageNotice() {
    const notice = document.getElementById('math-storage-notice');
    notice.hidden = storageAvailable;
    notice.textContent = storageAvailable ? '' : '当前为会话模式：复习标记未写入本机，刷新或关闭页面后会丢失。你可以继续本次复习。';
    document.getElementById('math-storage-summary').textContent = storageAvailable ? '复习标记仅保存在本机浏览器' : '会话模式 · 刷新后复习标记会丢失';
  }

  const subjectName = value => value === 'discrete' ? '离散数学' : '数值计算';
  cards.innerHTML = notes.map(note => `<article class="math-card" data-id="${note.id}" data-subject="${note.subject}">
    <div class="math-card-top"><span>${subjectName(note.subject)} / ${note.subject === 'discrete' ? 'CHAPTER' : 'METHOD'}</span><span class="math-card-number">${note.chapter}</span></div>
    <h3>${note.title}</h3><p class="math-card-intro">${note.intro}</p>
    <div class="math-card-formula">${note.formula}</div><ul class="math-card-list">${note.points.map(point => `<li>${point}</li>`).join('')}</ul>
    <details><summary>${note.question}</summary><div class="math-card-answer">${note.answer}</div></details>
    <div class="math-card-bottom"><span>${note.source}</span><button type="button" data-review="${note.id}" aria-pressed="${reviewed.has(note.id)}" aria-label="${note.title}：${reviewed.has(note.id) ? '取消已复习标记' : '标记为已复习'}">${reviewed.has(note.id) ? '✓ 已复习' : '○ 标记复习'}</button></div>
  </article>`).join('');

  const entries = [...cards.querySelectorAll('.math-card')].map((element, index) => ({ element, note: notes[index], text: (element.textContent + ' ' + notes[index].tags).toLowerCase() }));
  function updateExpandState() {
    const visible = entries.filter(entry => !entry.element.hidden);
    const allOpen = visible.length > 0 && visible.every(entry => entry.element.querySelector('details').open);
    expand.setAttribute('aria-expanded', String(allOpen));
    expand.textContent = allOpen ? '收起本页解答' : '展开本页解答';
  }
  function filter() {
    const terms = search.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
    let visible = 0;
    entries.forEach(entry => {
      const show = (subject === 'all' || entry.note.subject === subject) && terms.every(term => entry.text.includes(term)) && (!reviewOnly.checked || !reviewed.has(entry.note.id));
      entry.element.hidden = !show;
      if (show) visible++;
    });
    count.textContent = `${visible} / ${notes.length} 张知识卡 · 已复习 ${reviewed.size} 张`;
    empty.hidden = visible > 0;
    updateExpandState();
  }
  document.querySelectorAll('[data-subject]').forEach(button => {
    if (button.tagName !== 'BUTTON') return;
    button.addEventListener('click', () => {
      subject = button.dataset.subject;
      document.querySelectorAll('.math-filters button').forEach(tab => tab.setAttribute('aria-pressed', String(tab === button)));
      filter();
    });
  });
  cards.addEventListener('click', event => {
    const button = event.target.closest('[data-review]');
    if (!button) return;
    const id = button.dataset.review;
    reviewed.has(id) ? reviewed.delete(id) : reviewed.add(id);
    button.setAttribute('aria-pressed', String(reviewed.has(id)));
    button.textContent = reviewed.has(id) ? '✓ 已复习' : '○ 标记复习';
    const note = notes.find(item => item.id === id);
    button.setAttribute('aria-label', `${note.title}：${reviewed.has(id) ? '取消已复习标记' : '标记为已复习'}`);
    try {
      localStorage.setItem(storageKey, JSON.stringify([...reviewed]));
      storageAvailable = true;
    } catch (_) { storageAvailable = false; }
    updateStorageNotice();
    filter();
  });
  cards.querySelectorAll('details').forEach(details => details.addEventListener('toggle', updateExpandState));
  search.addEventListener('input', filter);
  reviewOnly.addEventListener('change', filter);
  expand.addEventListener('click', () => {
    const open = expand.getAttribute('aria-expanded') !== 'true';
    entries.filter(entry => !entry.element.hidden).forEach(entry => { entry.element.querySelector('details').open = open; });
    updateExpandState();
  });
  document.addEventListener('keydown', event => {
    if (event.key === '/' && !event.ctrlKey && !event.metaKey && !event.altKey && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName) && !document.activeElement.isContentEditable) {
      event.preventDefault(); search.focus();
    }
  });
  updateStorageNotice();
  filter();
})();
