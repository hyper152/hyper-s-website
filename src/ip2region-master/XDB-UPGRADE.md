# 网站使用的新版 IP 数据库

网站和 `src/analyze_visitor.py` 统一通过 `src/ip_location.py` 查询。
依赖：`pip install -r requirements.txt`（官方 `py-ip2region==3.0.4`）。

当前使用 `data/ip2region_v4.xdb` 和 `data/ip2region_v6.xdb`，按需加载到内存，支持并发查询。
来源为 https://github.com/lionsoul2014/ip2region ，固定提交、文件大小、SHA256 和数据库生成时间见 `data/xdb-manifest.json`。
新版字段是 `国家|省份|城市|ISP|ISO 国家代码`；国外地区名称可能为英文。

旧版 README、DB、原始数据和查询器仍保留，网站和分析脚本不再使用。
更新依赖或数据后，需重启正在运行的网站进程才能重新加载。
数据库只提供 IP 归属地信息，不代表访客实时精确位置。

如果当前 Python 没有安装 ip2region，自动使用 src/ip2region-master/_vendor/ip2region 中随项目保存的官方 3.0.4 查询库，无需切换环境。
