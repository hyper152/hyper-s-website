"""Build the public ACM reading library from learning source files only.

Usage: python src/import_acm_library.py --source <ACM source directory>
The import allowlist intentionally excludes documents, credentials, binaries and builds.
"""
from pathlib import Path
import argparse
import json
import re
import shutil

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', type=Path, default=Path('D:/.hyper/study/CS/ACM'), help='Directory containing the personal ACM learning archive')
parser.add_argument('--site', type=Path, default=Path(__file__).resolve().parents[1], help='Website root directory')
args = parser.parse_args()
source = args.source.resolve()
site = args.site.resolve()
target = site / 'pages/study/ACM'
media = site / 'media/pages/study/ACM'
media.mkdir(parents=True, exist_ok=True)
target.mkdir(parents=True, exist_ok=True)

# Review levels are editorial study guidance, never a platform's official difficulty.
# key | primary category | tags | review level | reading guide | things to verify
daily_text = '''
26.7.23|数学与数论|三角数,边界修正|基础|通过三角数定位层数，再比较区间端点；先用平方根估计，随后用整数不等式修正。|平方根是估计值，检查整数溢出与临界三角数。
26.7.24|动态规划|余数DP,滚动数组|进阶|把走完整圈转为对 n 的余数为 0；每步在余数状态上选择加或减。|新一轮必须清空 ndp；注意负数取模。
26.7.25|贪心与双指针|差分,贪心|进阶|差分统计每个高度的可削次数，从高到低优先取得 2H−1 的边际收益。|剩余操作不足以处理整层时，只消耗剩余次数。
26.7.26|枚举与位运算|二进制,有限枚举|基础|枚举至多 20 次加一，统计二进制末尾零，用乘二补足到 2 的 20 次方的倍数。|n 已整除时返回 0；移位和常量使用足够宽的整数。
26.8.7|模拟与实现|枚举,比较|基础|枚举双方两张牌的四种出牌顺序，逐局比较后累计获胜方案。|平局不会贡献正负分，方案按出牌下标区分。
26.8.8|图与树|DFS,二分染色,组合计数|进阶|沿树边交替染色，统计与根同色的点，再使用组合计数。|递归版本在长链上可能耗尽栈；复习时考虑迭代遍历。
26.8.9|动态规划|区间划分,gcd|进阶|预处理每个位置左右最近的非互质伙伴，再用前缀 DP 枚举合法分段。|原稿存在多层枚举，分析最坏时间再尝试优化。
26.8.10|贪心与双指针|滑动窗口,前后缀最值|进阶|用集合维护不重复窗口，同时预处理左右两侧操作成本的最小值。|集合中的值与窗口必须同步；留意空前缀和空后缀。
26.8.11|数学与数论|整数除法,分类讨论|基础|对 x=0、x=1 等情况分类，使用连续整除统计层数，避免浮点对数。|明确无解条件；y=0 与 x>y 的交界需要单独检查。
26.9.6|数据结构|ODT,区间赋值,map|挑战|用有序映射维护常值区间边界，split 后删除旧段，并同步各值覆盖长度。|原稿 Split 直接读取 lower_bound 的结果，末尾边界可能为 end；复习时补哨兵并验证边界。
26.9.7|构造|贪心,数组填充|进阶|先让未知位置延续邻近值，求当前陡峭值，再尝试调整端点完成目标。|全零、单元素、端点不可修改等情况需要分别验证。
26.9.8|数学与数论|排序,贡献法,模逆元|进阶|排序后按每个元素在两两差中的贡献系数求和，用快速幂求模逆元。|负数取模需归一化；逆元成立依赖模数与分母条件。
26.9.9|动态规划|前缀和,区间DP|进阶|记录每个值第一次出现的位置，以前缀和计算成对端点区间得分并转移。|转移从 dp[p−1] 出发，避免把已删除区间重复计算。
26.9.10|枚举与位运算|二维枚举,矩形覆盖|基础|对每个被标记位置枚举能覆盖它的 k×k 窗口，并记录可行起点。|先证明复杂度适合题目规模；起点范围应限制在网格内。
26.9.11|贪心与双指针|字符串分段,贪心|进阶|扫描连续字符段，比较相邻段的贡献，维护可取方案与最大值。|检查首尾连续 2 的特殊分支，并为贪心选择给出理由。
26.9.12|数学与数论|进制转换,数位|基础|不断除以 k，取余获得各个数位，维护最大的数位。|k=1 必须单独处理，防止循环不终止。
26.9.13|动态规划|状压DP,行状态|挑战|枚举单行合法摆放掩码，结合地形与前两行状态进行转移。|检查横向间隔、相邻两行冲突以及不可达状态初始化。
26.9.14|数学与数论|容斥,子集枚举|挑战|枚举条件子集，用最小公倍数统计倍数数量，按子集奇偶进行容斥。|乘积或 lcm 可能溢出，先做除法界限判断再相乘。
26.9.15|构造|数学,区间端点|进阶|先推导可行区间范围，再把多出的长度分配到左右端点。|检查可行性上下界与端点是否仍满足题目的正数限制。
26.9.16|图与树|BFS,余数状态|挑战|把格点与当前余数组合成状态 (x,y,rem)，用 BFS 求最少步数。|不能只按坐标去重；同一格点的不同余数是不同状态。
26.9.17|图与树|Tarjan,强连通分量,缩点|挑战|Tarjan 求强连通分量，缩点后检查出度为 0 的分量并统计候选。|原稿在栈内已访问邻点分支使用 low[v]，标准写法使用 dfn[v]；对照 AI 参考复核强连通分量边界。
26.9.18|构造|异或,不变量|基础|利用 0 的异或恒等性质，把贡献集中到一个元素，构造其余为 0。|提交前回到题面确认元素范围与是否允许 0。
26.9.19|数学与数论|乘法原理,字符串|进阶|按相邻 1 之间连续 0 的长度分解选择数，独立段的方案相乘。|首尾零段与中间零段的计数规则不同。
26.9.20|贪心与双指针|逐项上界,求和|基础|逐项取两种限制的较小值求可供货总量，再与总需求取最小值。|累计量可能超过 int，使用 long long。
26.9.21|模拟与实现|随机数,二维数组|进阶|按题面伪随机生成器产生操作，在网格中模拟填充和删除并计算异或校验。|原稿把 op==2 嵌在 op==1 分支内，删除操作无法触发；行列下标范围也需要核对。
26.9.22|数学与数论|二叉树,二进制,等比数列|进阶|分离完整树层数与剩余节点，把剩余数量按二进制拆开累计贡献。|原文件仅定义 solve，缺少 main；先补入口再提交。移位上界与取模时机也需检查。
26.9.23|贪心与双指针|双指针,倍增,函数复合|挑战|先用双指针建立每个点的一次跳转，再按跳跃次数的二进制位复合映射。|等距离时的选择规则必须与题面一致；倍增时使用独立 nextJump。
26.9.24|贪心与双指针|装箱,分类讨论|挑战|按大尺寸物品优先装入，再计算剩余空位可容纳的小尺寸物品。|每种余数情形的空位数量需独立推导，不宜仅凭面积判断。
26.9.25|动态规划|网格DP,滚动数组|进阶|从三角形底部允许的终点向上转移，每格取下层三个邻位的最大值。|不可达状态必须设负无穷；负权数据不能被默认 0 状态覆盖。
26.9.26|字符串|格式化,分类讨论|基础|按降幂拼接非零项，分别处理符号、系数 ±1、常数项与一次项。|原稿以 i==n 判断首项，首部系数为 0 时易多出加号；全零多项式也需处理。
26.9.27|图与树|树形DP,子树统计|挑战|先迭代建立父子关系，逆序合并子树颜色信息，再统计删除边两侧的差异。|原稿最终枚举 i<n，没有处理编号 n 的点；对照 AI 参考核对边枚举范围。
26.9.28|数学与数论|质因数分解,二分,阶乘指数|进阶|分解 p 的质因子，用 Legendre 公式计算 n! 中的指数，再二分最小 n。|质因数分解的终止条件、p=1、剩余大质因子应独立检查。
26.9.29|字符串|KMP,前缀函数,子串匹配|进阶|原稿用 find 枚举匹配起点，再计算模式串前缀函数；复习时可改为完整 KMP 扫描。|匹配后只前进 1 位才能保留重叠出现；分析 find 的最坏复杂度。
26.9.30|动态规划|二维背包,路径还原|挑战|以两组元素的和作为二维状态，保存正负来源标记，查询时枚举乘积分解并还原选择。|压缩后的不规则二维数组需要特别核对下标；倒序更新防止重复使用同一元素。
26.10.1|图与树|有向树,入度,叶子|基础|有向边标记孩子，未作为孩子出现的点为根，没有孩子的点为叶子。|单节点树同时是根和叶子；输出叶子前按编号排序。
26.10.2|动态规划|阶段DP,滚动数组|进阶|每道题先计算当前状态的得分，再枚举保持、减 Q、加 W 三种状态转移。|同一轮必须读旧数组、写新数组，不能把同一道题重复转移。
26.10.3|构造|前缀最大值,贪心|基础|扫描维护前缀最大值，输出把当前值补到该最大值所需的增量。|初始最大值要低于所有合法输入；不应把输入默认成非负。
26.10.4|图与树|树直径,BFS,离心率|进阶|三次 BFS 找到直径两端，节点最远距离等于到这两个端点距离的较大值。|保留的 O(n²) 注释稿可对照理解；正式思路用线性遍历。
26.10.5|字符串|循环移位,整除规则|基础|枚举旋转次数，用旋转后末两位判断能否被 4 整除。|长度为 1 时不能把同一个数位当作两位数，需要单独核对。
26.10.6|数据结构|区间修改,差分,树状数组|进阶|原稿逐个增加区间元素，再回答单点查询；可用差分与树状数组优化。|当前实现单次修改为 O(n)，总量大时有超时风险；模板速查附树状数组写法。
26.10.16|动态规划|字符串,线性DP|基础|若相邻字符相同，用 dp[i−2]+2 延长可配对的偶数长度子串。|固定数组容量依赖题面长度；应明确状态表示以免与普通最大子段和混淆。
26.10.17|贪心与双指针|中位数,前缀和,滑动窗口|进阶|排序后窗口统一成中位数的代价最小，用前缀和 O(1) 计算代价并移动左端点。|两侧代价公式易差 1；窗口缩小到单点时费用应为 0。
26.10.18|数学与数论|整除分块,等差数列|进阶|把 k mod i 写成 k−floor(k/i)·i，按商相等的区间整块求和。|商为 0 时及时结束；区间乘积应考虑中间溢出。
26.10.19|字符串|栈,环形消除,双指针|进阶|先用栈消去相邻相同字符，再用双指针处理剩余串首尾可消除的部分。|原稿在判断 l<r 前读取 tmp[l]、tmp[r]；全消除时空串访问越界，需先检查边界。
26.10.20|数学与数论|质因数分解,贪心|进阶|按从小到大的质因子逐次缩小剩余量，累加每一步的贡献。|解释为何优先除小质因子；最后剩余的大质因子需要补贡献。
26.10.21|数学与数论|组合恒等式,快速幂|进阶|用组合恒等式把求和化为 n(n−1)·2^(n−3)，再快速幂取模。|n=1、n=2 单独返回，避免出现负指数。
26.10.22|图与树|树的重心,子树大小,迭代DFS|进阶|先得到父子遍历序，逆序计算子树大小，检查删点后的最大连通块是否至多 n/2。|这份代码以树为前提；一般图需要 visited 与不同算法。
26.10.23|数学与数论|gcd,比例不变量,整数区间|基础|同时乘除保持最简比例不变；约去最大公约数后，可达整数对均为该最简整数对的正整数倍，转为求倍数 k 的可行区间。|原稿用 / 约分会转成浮点，且 k 上界用了向上取整；应使用 // 约分，以 ceil(l/min(x,y)) 与 floor(r/max(x,y)) 为界，计数需截到至少 0。
'''

contest2025 = '''
A|动态规划|有限状态,费用最小化|挑战|用 9 个状态记录上一次操作费用，逐个字符选择下一次读取或跳过。|状态编号并非实际费用；不可达状态相加前要判断。
B|模拟与实现|分支,字典映射|基础|把输入的单个字符映射成固定输出。|固定字符串的大小写与标点要完全匹配。
C|数学与数论|贡献法,等差数列,奇偶性|挑战|将 01 与 10 的数量差转成各个 1 的位置贡献，枚举可修改区间内放置的 1 的数量。|同时检查贡献上下界和步长为 2 的奇偶条件。
D|交互|二分,有理数,flush|挑战|AI 参考通过最简分数进行查询，在候选范围中逐步缩小答案。|hyper 原稿仅输入 n，未完成；交互输出必须刷新并处理读取结束。
E|数学与数论|区间,线性约束,分类讨论|挑战|按两个输出区间的覆盖类型，提取 u、v、u+v 的已知约束。|原稿与 AI 参考需对照验证，重复信息不等于多解。
F|数据结构|数论,分组和,multiset|挑战|按 n 的不同质因子得到候选步长，维护模类之和及动态最大贡献。|hyper 原稿只保留一个步长；对比 AI 参考理解为什么需要多个候选。
G|数学与数论|等差数列,溢出|基础|将最大围住点数归纳为 0+1+…+(m−1)。|hyper 原稿使用 int 做乘法，范围大时溢出；参考版改用 long long。
H|动态规划|区间状态,切比雪夫距离|挑战|AI 参考用已建点的坐标包围盒刻画后续距离费用，再进行状态转移。|hyper 原稿仅保留骨架，先从 AI 注释理清状态边界。
I|贪心与双指针|分组,排序,滑动窗口|进阶|分别按横坐标、纵坐标分组，在各组内排序并寻找跨度不超过 5 的窗口。|同组数据要排序；左右端点随窗口同步移动。
J|图与树|深度奇偶,树,组合计数|进阶|树上两点距离为偶数等价于深度同奇偶，分别从两类节点中选两个。|hyper 原稿仅输入 n；AI 参考使用迭代遍历避免递归深度风险。
K|模拟与实现|2048,方向分支|基础|对 2×2 棋盘按方向比较并合并相同非零格，再压缩空位。|一次移动中同一格是否可重复合并要遵守题意。
L|字符串|仿射映射,取模,输入解析|进阶|解析整行单词与密钥，按字符差值及模 26 的变换输出。|字符偏移转为非负余数；空格和换行要保持正确。
M|数学与数论|分段函数,加权平均,浮点|基础|按成绩分段计算绩点，累计学分乘绩点后除以总学分。|除法要使用浮点类型；输出精度不足会造成误差。
'''

contest2026 = '''
A|数据结构|map,set,懒偏移|挑战|把位置转成固定坐标，维护按位置与按体积的两份索引，全体平移只改 offset。|每次增删改需同步两个容器；位置为 0 也入海。
B|动态规划|状态压缩,字符串,子序列计数|挑战|用消除后交替串的首尾两位表示状态，按最后选中位置统计能消成一位的子序列。|首尾相同不代表仅剩一位；每轮转移必须读旧 dp。
C|字符串|数位模拟,大整数|基础|把两数作为字符串从低位对齐，每位相加取模 10，再去除前导零。|至少保留一个 0，避免结果为空。
D|动态规划|相邻交换,逆序对,有限排列|挑战|枚举 0122 的 12 种排列，四阶段 DP 选位置，把聚拢费用与内部逆序对费用相加。|阶段倒序更新，不能重复选同一位置；状态值可以为负。
E|动态规划|线性DP,相邻配对|进阶|只看最后一单，枚举第 i 人独买或最后两人拼单，得到前缀最小费用。|不能将原本不相邻的人拼单；注意半价的数值精度。
F|数学与数论|质因子指数,线性方程|基础|只维护 2 与 3 的指数，设乘 6 与除 2 次数，解非负整数条件。|先做乘法再做除法可保证操作合法，不必生成大整数。
G|数据结构|栈,区间模拟,操作编号|进阶|每个位置用栈保存覆盖层及操作编号，撕除时向两侧连续弹出同编号的顶层。|逐位置粘贴与撕除最坏为 O(nq)，存储所有覆盖层也需评估；对照 ERROR 原稿检查空栈。
H|数学与数论|前缀和,前后缀最小值|进阶|枚举余额翻倍的时机，用前后缀最小值推导启动资金的两个下界。|前缀最小值必须包含初始 0；整除上取整方向要正确。
I|图与树|树上配对,后序遍历|挑战|每棵子树最多上传一个未配对特殊点，在父节点处将来自不同分支的点配对。|pending 记录节点编号，不是个数；路径允许共点但不能共边。
J|动态规划|排序,相邻配对,最小子段|挑战|原点排序后相邻配对，插入两点会翻转一段黑白间隙，把增量转成最小连续区间和。|按位置区分段的正负权；最优新端点可落在原点上。
K|数学与数论|生成函数,Horner,整数根|挑战|用多项式 ∏(p_i+x) 表示零的计数，枚举 1..20，用 Horner 求 F(−t) 找回整数根。|系数可能很大，Python 可用任意精度；C++ 参考需要核对整数范围。
L|构造|网格路径,蛇形遍历,分类讨论|进阶|先在前 k−1 列交替上下移动，再走完剩余列并折返，覆盖两行所有格子且恰好竖直移动 k 次。|可行范围为 1≤k≤n；k=1 时须补上另一行第一格，n=1 单独处理。
M|图与树|换根DP,颜色,有向边消息|挑战|每个方向记录这一侧能否缩并与最终颜色，用两遍遍历推导所有根的可行性。|hyper 文件为空；AI 参考的颜色公式仅在该方向可行时有效。
N|模拟与实现|字典映射,查表|基础|固定七种姓名缩写与学校缩写的映射，读入后查表输出。|键要完整匹配；题目保证之外的输入不能默认插入空值。
'''

nowcoder_text = '''
1B|计算几何|建图,Dijkstra,圆弧|挑战|把端点作为节点，以圆弧长度和同角径向距离建立带权图，运行 Dijkstra。|角度存在循环区间；double 精度和不可达情况需核对。
3K|计算几何|叉积,方向判断|基础|对连续三点的两段向量取叉积，符号对应左转、右转或直行。|乘法可能超过 int，使用 long long；共线时输出 STRAIGHT。
4I|字符串|循环字符串,匹配|进阶|将 S 拼接成 S+S，搜索 Rounddo 加 k 个 g 的模式串，统计环上出现。|复制串中的匹配并非全部对应不同环上起点；核对范围与重复计数。
7G|待补全|空文件|待补全|目录保留了题名，但源码文件为空，作为后续补题占位。|当前没有足够代码依据进行算法分类。
7K|字符串|缩写,map,冲突消解|进阶|先取单词首字母作为缩写，将冲突组逐轮展开更多完整单词。|若所有单词已展开仍有相同姓名，原循环可能不终止；需核对题目保证。
7L|数学与数论|取模,分块计数,枚举|进阶|枚举 b，将满足条件的 a 写成若干连续区间，累加区间长度。|当前还有内层区间枚举，需要分析最坏复杂度。
8I|贪心与双指针|极值,分类讨论|进阶|按每一对数的大小与预算分别统计可能赢下的最少、最多数量。|严格大于与大于等于不可混淆；每对的分支必须互斥。
9B|模拟与实现|行列计数,最小值|基础|行、列计数初始化为 n，每次读入标记坐标后同时减去相应行列的剩余量，最后取最小值。|若输入可能重复标记同一格，需要去重；是否允许重复应依据原题保证。
9H|数学与数论|奇偶性,set,去重|进阶|用总奇数个数与候选值奇偶性判断，分别统计已出现及未出现的偶数和奇数。|集合去重后的数量与原数组奇数数量承担不同含义。
'''

def parse(text):
    rows = {}
    for line in text.strip().splitlines():
        fields = line.split('|')
        if len(fields) != 6:
            raise ValueError(line)
        key, category, tags, level, summary, caution = fields
        rows[key] = dict(category=category, tags=tags.split(','), level=level, summary=summary, caution=caution)
    return rows

maps = dict(daily=parse(daily_text), c2025=parse(contest2025), c2026=parse(contest2026), nowcoder=parse(nowcoder_text))

def require_metadata(group_name, key, relative_path):
    if key not in maps[group_name]:
        raise ValueError(f'学习题档尚未整理：{relative_path}。请先补充该题的独立分类与元数据，再重新导入。')
    return maps[group_name][key]

groups = {}
source_files = sorted(p for p in source.rglob('*') if p.is_file() and p.suffix.lower() in {'.cpp', '.py'} and not any(x.lower() in {'build', '.git', '__pycache__'} for x in p.relative_to(source).parts))

def read_text(path):
    data = path.read_bytes()
    for encoding in ('utf-8-sig','gb18030'):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError(f'Unsupported text encoding: {path}')

for p in source_files:
    rel = p.relative_to(source).as_posix()
    if rel == 'init.cpp':
        continue
    code = read_text(p)
    stem = re.sub(r'-(?:hyper|hyp|AI|AC)$', '', p.stem)
    if rel.startswith('daily/'):
        key = re.match(r'\d+\.\d+\.\d+', stem).group()
        title = stem[len(key)+1:]
        # Filenames contain useful algorithm prefixes; keep those as tags instead of in titles.
        prefix_tags = {'DP','数论','数学','枚举','位运算','差分','贪心','双指针','树','DFS','模拟','二维枚举','进制','状压DP','容斥原理','构造','BFS','异或','二叉树','ODT','排序'}
        parts = title.split('-')
        while len(parts)>1 and parts[0] in prefix_tags:
            parts.pop(0)
        title = '-'.join(parts)
        meta = require_metadata('daily', key, rel)
        uid = 'daily-'+key.replace('.','-')
        source_name = '日常训练'
        platform = '本地题档'
        yy,mm,dd = key.split('.')
        date = f'20{yy}-{int(mm):02}-{int(dd):02}'
        group = 'daily'
    elif rel.startswith('2025重庆'):
        letter = stem[0]
        uid, title = 'cqu2025-'+letter, stem[2:]
        meta, source_name, platform, date, group = require_metadata('c2025', letter, rel), '2025 重庆大学新生赛', '校内竞赛', '', 'c2025'
    elif rel.startswith('2026重庆'):
        letter = stem[0]
        uid, title = 'cqu2026-'+letter, stem[2:]
        meta, source_name, platform, date, group = require_metadata('c2026', letter, rel), '2026 重庆大学新生赛', '校内竞赛', '', 'c2026'
    elif rel.startswith('2026ICPC'):
        if p.relative_to(source).parts[:2] != ('2026ICPC网络赛', '2') or stem not in {'J', 'K', 'L'}:
            raise ValueError(f'ICPC 题档尚未整理：{rel}。请先补充该轮次和题号的元数据，再重新导入。')
        letter = stem[0]
        uid, title = 'icpc2026-r2-'+letter, 'Problem '+letter
        source_name, platform, date, group = '2026 ICPC 网络赛 · 第二场', 'QOJ', '', 'icpc'
        if letter=='J':
            meta=dict(category='字符串',tags=['模式匹配','计分','分支'],level='基础',summary='将六类字符串模式对应到固定分数，匹配后累计并与阈值比较。',caution='模式末尾字母的有效范围需遵守题意；输出的固定字符串要完全匹配。')
        elif letter=='K':
            meta=dict(category='数据结构',tags=['mex','频次','配对','记忆化'],level='挑战',summary='按 {t,k−t} 成对分配频次，把每一对对 mex 的约束合并，并缓存重复 k 的结果。',caution='AI 参考对小 k 的不同询问逐一枚举，最坏复杂度仍需依据数据范围评估。')
        elif letter=='L':
            meta=dict(category='数学与数论',tags=['路径转化','一维游走','贪心'],level='挑战',summary='用 d=i−j 将循环移位网格路径变成一维往返，枚举最低代价边重复经过的最优结构。',caution='d 本身不取模，只有读权值时取模；起点权值只单独计一次。')
    elif rel.startswith('牛客多校/'):
        round_no = p.relative_to(source).parts[1]
        letter = stem[0]
        uid, title = f'nowcoder-r{round_no}-{letter}', re.sub(r'^[A-Z][\s-]+','',stem)
        meta = require_metadata('nowcoder', round_no+letter, rel)
        source_name, platform, date, group = f'2026 牛客多校 · 第 {round_no} 场', '牛客', '', 'nowcoder'
    elif rel.startswith('洛谷/'):
        problem_match = re.match(r'^(P\d+)(?:\s|$)', stem)
        if not problem_match or problem_match.group(1) != 'P1027':
            raise ValueError(f'洛谷题档尚未整理：{rel}。请先补充独立题号及元数据，再重新导入。')
        uid, title = 'luogu-P1027', 'P1027 · Car 的旅行路线'
        meta=dict(category='图与树',tags=['Floyd','矩形补点','计算几何'],level='挑战',summary='用点积确定矩形直角顶点并补齐第四点，建立城市内外交通费用，再用 Floyd 求最短路。',caution='几何坐标乘积需足够宽的整数；距离和费用用浮点数，核对出发到达城市的所有机场。')
        source_name, platform, date, group = 'NOIP 2001 提高组', '洛谷', '', 'luogu'
    else:
        raise ValueError(f'Unclassified source file: {rel}')
    if uid not in groups:
        groups[uid] = dict(id=uid,title=title,source=source_name,platform=platform,date=date,group=group,**meta,versions=[],statement='',links=[])
    item = groups[uid]
    is_ai = '/AI/' in rel or '-AI.' in rel
    is_error = '/ERROR/' in rel
    is_ac = '/AC/' in rel
    cleaned = re.sub(r'/\*.*?\*/|//[^\n]*', '', code, flags=re.S)
    incomplete = not code.strip() or (p.suffix=='.cpp' and (not re.search(r'\bmain\s*\(',cleaned) or (not re.search(r'cout|printf|puts|putchar|ask\s*\(',cleaned))))
    status = 'empty' if not code.strip() else 'incomplete' if incomplete else 'error' if is_error else 'ac-directory' if is_ac else 'reference' if is_ai else 'original'
    labels = {'empty':'空文件 · 待补全','incomplete':'未完成稿','error':'ERROR 目录原稿','ac-directory':'AC 目录存档','reference':'AI 参考','original':'hyper 原稿'}
    item['versions'].append(dict(name=labels[status],language='Python' if p.suffix=='.py' else 'C++',status=status,path=rel,code=code))
    # Prefer a detailed leading AI annotation as the reading note, preserving provenance.
    if is_ai:
        block = re.match(r'\s*/\*(.*?)\*/',code,re.S)
        if block and len(block.group(1).strip())>50:
            item['editorial']=block.group(1).strip()
            item['editorialSource']='原文件中的 AI 参考注释 · 请结合题面与原稿复核'
    if uid=='luogu-P1027':
        item['links']=[dict(label='洛谷 P1027 题面',url='https://www.luogu.com.cn/problem/P1027')]
    if group=='icpc':
        # Provenance: 2026ICPC网络赛/2/QOJ链接.md in the original archive.
        item['links']=[dict(label='题档中的 QOJ 链接',url='https://qoj.ac/contest/4113')]
    for url in re.findall(r'https://(?:www\.)?nowcoder\.com/discuss/[0-9]+',code):
        if not any(x['url']==url for x in item['links']):
            item['links'].append(dict(label='源码内的牛客题解链接',url=url))

# Daily question posters are imported only from the explicit image directory.
for p in sorted((source/'daily/img').iterdir()):
    if p.suffix.lower() not in {'.jpg','.jpeg','.png','.webp'}:
        continue
    m=re.match(r'(\d+\.\d+\.\d+)-',p.stem)
    if not m:
        continue
    uid='daily-'+m.group(1).replace('.','-')
    if uid not in groups:
        raise ValueError(f'Orphaned question poster: {p.name}')
    new_name=uid+p.suffix.lower()
    shutil.copy2(p,media/new_name)
    groups[uid]['statement']='/media/pages/study/ACM/'+new_name

rank={'ac-directory':0,'original':1,'reference':2,'error':3,'incomplete':4,'empty':5}
items=sorted(groups.values(),key=lambda x:(x['date'] or '0000',x['source'],x['id']),reverse=True)
for item in items:
    item['versions'].sort(key=lambda v:(rank[v['status']],v['language']))
    if item['group'] not in {'daily','luogu'}:
        match=re.search(r'-([A-Z])$',item['id'])
        if match:
            item['number']=match.group(1)
    item['hasIssues']=any(v['status'] in {'empty','incomplete','error'} for v in item['versions']) or item['id'] in {'daily-26-9-6','daily-26-9-17','daily-26-9-21','daily-26-9-22','daily-26-9-26','daily-26-9-27','daily-26-10-5','daily-26-10-6','daily-26-10-19','daily-26-10-23','cqu2025-F','cqu2025-G'}

payload=dict(updated='2026-10-23',items=items,counts=dict(problems=len(items),versions=sum(len(x['versions']) for x in items),posters=sum(bool(x['statement']) for x in items),categories=len(set(x['category'] for x in items))))
serialized=json.dumps(payload,ensure_ascii=False,separators=(',',':'))
(target/'library-data.js').write_text('window.ACM_LIBRARY = '+serialized+';\n',encoding='utf-8')
print(json.dumps(payload['counts'],ensure_ascii=False))
