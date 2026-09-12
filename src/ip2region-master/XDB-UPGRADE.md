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

## IPv6 数据源切换（2026-09-11）

IPv4 继续使用官方 ip2region 数据。IPv6 改为 fa1seut0pia/ip2region-xdb 的 2026.09.10 release（GeoCN + GeoLite2 融合），完整来源、SHA256 和字段格式见 manifest 中各文件条目；不再使用原官方 IPv6 字段格式。

- 发布：https://github.com/fa1seut0pia/ip2region-xdb/releases/tag/2026.09.10
- 中国数据：https://github.com/ljxi/GeoCN（不定期更新，来源为公开 API 整理）
- 全球数据：https://github.com/P3TERX/GeoLite.mmdb ，含 MaxMind GeoLite2 数据 https://www.maxmind.com 。转换程序 MIT 授权不代表上游数据的授权；上游数据使用条件仍适用。
- IPv6 字段：洲|国家|省份|城市|区县|ISP|网络类型。城市为空时回退到省份，不推测城市。

本地抽样：用户提供的移动 IPv6 在新库为浙江省，城市缺失，不能声称已经定位到温州；之前两个电信 IPv6 在新库为重庆市。抽样差异不等于全面准确率验证，也没有批量发送访问日志到在线查询服务。重启网站后新查询生效；旧日志不会回写。
