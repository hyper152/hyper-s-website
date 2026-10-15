"""将指定旧站备份整理为静态快照：页面在 projects/web，媒体按页面路径归档。"""
import argparse
from collections import defaultdict
from contextlib import closing
import html
import json
from pathlib import Path
import posixpath
import re
import shutil
import sqlite3
from urllib.parse import quote, unquote, urlsplit

from jinja2 import Environment

VERSIONS = ('py.hyper152.love', 'py.0o0hyper0o0.cyou', 'hyper152.love', 'hyper152.cn')
CODE = {'.html', '.htm', '.css', '.js'}
MEDIA = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.ico', '.svg', '.mp4', '.mp3', '.avi',
         '.pdf', '.woff', '.woff2', '.ttf', '.eot', '.otf'}
BASE = '/pages/projects/web/'
MEDIA_BASE = '/media/pages/projects/web/'
URL_ATTR = re.compile(r'''(\b(?:href|src|poster|action|data-original)\s*=\s*)(["'])(.*?)\2''', re.I | re.S)
CSS_URL = re.compile(r'''url\(\s*(["']?)(.*?)\1\s*\)''', re.I)


def public_path(relative):
    return '/'.join(part.lstrip('.') if part in ('.hyp', '.人物志') else part for part in relative.parts)


def url_path(value):
    return quote(value, safe='/.-_~')


def navigation(version):
    return f'''<nav id="legacy-toolbar" aria-label="旧版页面导航">
<a href="{BASE}{version}/catalog.html" data-page-back>← 返回上一页</a>
<a href="/pages/home/">⌂ 首页</a>
<a href="{BASE}#legacy-sites">旧版网站</a>
<a href="{BASE}{version}/catalog.html">浏览该版本</a>
<small>{html.escape(version)} · 历史快照</small></nav>'''


def snapshot_document(content, version):
    # 旧页中包含无 body、提前关闭 body 等写法，统一外壳后保留原有内容和样式。
    content = re.sub(r'<body\s*(?=<)', '<body>', content, flags=re.I)
    content = re.sub(r'<meta\b[^>]*http-equiv\s*=\s*["\']?refresh["\']?[^>]*>', '', content, flags=re.I)
    heads = re.findall(r'<head\b[^>]*>(.*?)</head\s*>', content, flags=re.I | re.S)
    content = re.sub(r'<head\b[^>]*>.*?</head\s*>', '', content, flags=re.I | re.S)
    extra_head = re.findall(r'<(?:title|style)\b[^>]*>.*?</(?:title|style)\s*>', content, flags=re.I | re.S)
    content = re.sub(r'<(?:title|style)\b[^>]*>.*?</(?:title|style)\s*>', '', content, flags=re.I | re.S)
    content = re.sub(r'<!doctype[^>]*>|</?(?:html|body)\b[^>]*>', '', content, flags=re.I)
    head = '\n'.join([*heads, *extra_head])
    if not re.search(r'<title\b', head, re.I):
        head += f'<title>{html.escape(version)} · 旧版页面</title>'
    return f'''<!doctype html><html lang="zh-CN"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
{head}<link rel="stylesheet" href="{BASE}archive.css?v=20261014-1">
</head><body data-legacy-snapshot="true">{navigation(version)}
{content}<script src="/pages/_shared/page-navigation.js?v=20260911-1" defer></script>
</body></html>'''


def catalog_document(version, pages, media, messages):
    groups = defaultdict(list)
    for path, target in pages:
        if '/error/' in path or path.startswith('templates/error/'):
            group = '当年的错误页面'
        else:
            group = path.split('/')[0] if '/' in path else '首页与留言'
        label = path[:-len('/index.html')] if path.endswith('/index.html') else path
        groups[group].append((label, target))
    for path, target in media:
        if Path(path).suffix.lower() in ('.pdf', '.mp4', '.avi', '.mp3'):
            groups['文档与视频'].append((path, target))
    sections = []
    for group, items in groups.items():
        links = ''.join(f'<a href="{url_path(target)}">{html.escape(label)} <span>↗</span></a>'
                        for label, target in sorted(items))
        sections.append(f'<section class="archive-group"><h2>{html.escape(group)}</h2><div class="archive-links">{links}</div></section>')
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#f6f7f2">
<title>{html.escape(version)} · 旧版内容目录</title>
<link rel="stylesheet" href="/pages/_shared/site-theme.css?v=20260911-centered-navigation">
<link rel="stylesheet" href="{BASE}archive.css?v=20261014-1"></head>
<body data-site-theme="garden">{navigation(version)}<main class="archive-catalog">
<p class="archive-eyebrow">THE EARLIER DAYS</p><h1>{html.escape(version)}</h1>
<p class="archive-intro">{len(pages)} 个页面 · {len(media)} 个媒体文件{f' · {messages} 条历史记录' if messages else ''}</p>
<div class="archive-catalog-actions"><a href="{BASE}{version}/">打开旧版首页 →</a><a href="{BASE}#legacy-sites">所有旧版网站</a></div>
{''.join(sections)}</main><script src="/pages/_shared/page-navigation.js?v=20260911-1" defer></script></body></html>'''


def import_sites(source_dir, project):
    source_dir, project = Path(source_dir).resolve(), Path(project).resolve()
    versions = {}
    for version in VERSIONS:
        root = source_dir / version
        if not root.is_dir():
            raise FileNotFoundError(root)
        files = {}
        for path in sorted(root.rglob('*')):
            if not path.is_file():
                continue
            if not path.resolve().is_relative_to(root):
                raise ValueError(f'备份目录中的链接越界: {path}')
            relative = path.relative_to(root)
            if any(part.startswith('.') and part not in ('.hyp', '.人物志') for part in relative.parts):
                continue
            suffix = path.suffix.lower()
            if suffix not in CODE | MEDIA and path.name.lower() not in ('license.txt', 'license'):
                continue
            if suffix in ('.html', '.htm') and re.search(r'<\?(?:php|=)', path.read_text(encoding='utf-8-sig', errors='replace'), re.I):
                continue
            if suffix in ('.js', '.css') and 'discuss' in relative.parts:
                continue
            mapped = public_path(relative)
            prefix = MEDIA_BASE if suffix in MEDIA else BASE
            files[relative.as_posix().casefold()] = {'source': path, 'relative': mapped,
                                                       'target': prefix + version + '/' + mapped}
        versions[version] = {'root': root, 'files': files, 'messages': []}
        db_path = root / 'data/data.db'
        if db_path.is_file():
            with closing(sqlite3.connect(db_path.as_uri() + '?mode=ro', uri=True)) as db:
                versions[version]['messages'] = db.execute('SELECT name,classid FROM students ORDER BY rowid').fetchall()

    missing = set()
    basename_maps = {}
    for version, site in versions.items():
        names = defaultdict(list)
        for item in site['files'].values():
            names[item['source'].name.casefold()].append(item)
        basename_maps[version] = names

    def rewrite_url(value, version, source_relative):
        value = value.strip()
        if value.startswith((BASE, MEDIA_BASE)):
            return value
        if not value or value.startswith('#'):
            return value
        parsed = urlsplit(value.replace('\\', '/'))
        host = (parsed.hostname or '').lower().removeprefix('www.')
        if parsed.scheme or parsed.netloc:
            if host not in versions:
                return value
            target_version = host
            relative = unquote(parsed.path).lstrip('/')
        else:
            target_version = version
            relative = unquote(parsed.path)
            if not relative.startswith('/'):
                relative = posixpath.join(posixpath.dirname(source_relative), relative)
            relative = posixpath.normpath(relative.lstrip('/'))
        if relative in ('', '.', '/'):
            target = BASE + target_version + '/'
        elif relative.rstrip('/') in ('login', 'talk'):
            target = BASE + target_version + ('/qiandao.html' if relative.rstrip('/') == 'login' else '/')
        else:
            key = relative.rstrip('/').casefold()
            item = versions[target_version]['files'].get(key) or versions[target_version]['files'].get(key + '/index.html')
            if item is None:
                matches = basename_maps[target_version].get(posixpath.basename(key), [])
                if len(matches) == 1:
                    item = matches[0]
            if item is None:
                missing.add((target_version, source_relative, value))
                return value
            target = item['target']
        return url_path(target) + ('?' + parsed.query if parsed.query else '') + ('#' + parsed.fragment if parsed.fragment else '')

    environment = Environment(autoescape=True)
    report = []
    for version, site in versions.items():
        pages, media = [], []
        for key, item in site['files'].items():
            source, target = item['source'], project / item['target'].lstrip('/')
            if not target.resolve().is_relative_to(project):
                raise ValueError('导入目标越界')
            target.parent.mkdir(parents=True, exist_ok=True)
            suffix = source.suffix.lower()
            if suffix in MEDIA:
                shutil.copy2(source, target)
                media.append((item['relative'], item['target']))
                continue
            content = source.read_text(encoding='utf-8-sig', errors='strict')
            if suffix in ('.html', '.htm'):
                if source.name == 'qiandao.html':
                    content = content.replace('{{name}}，留言成功', '历史留言（只读）')
                    content = environment.from_string(content).render(data=site['messages'], name='历史访客')
                if source.name == 'comment.html':
                    content = re.sub(r'(<form\b)[^>]*>', r'\1 action="' + BASE + version + '/qiandao.html" method="get">', content)
                    content = re.sub(r'(<input\b[^>]*)(>)', r'\1 disabled\2', content)
                    content = content.replace('>签到<', '>查看历史留言<')
                    content = content.replace('<div class="login-container">', '<div class="login-container"><p>旧版留言板 · 只读留存</p>')
                content = URL_ATTR.sub(lambda match: match[1] + match[2] + rewrite_url(match[3], version, key) + match[2], content)
                content = CSS_URL.sub(lambda match: 'url("' + rewrite_url(match[2], version, key) + '")', content)
                content = snapshot_document(content, version)
                pages.append((item['relative'], item['target']))
            elif suffix == '.css':
                content = CSS_URL.sub(lambda match: 'url("' + rewrite_url(match[2], version, key) + '")', content)
            elif suffix == '.js' and source.name == 'main.js' and 'getAchives' in content:
                # 历史主页只保留当年的交互，不拉取第三方实时文章或一言。
                content = re.sub(r'^\s*(?:getAchives|gethitokoto)\(\);\s*$', '', content, flags=re.M)
            target.write_text(content, encoding='utf-8')

        primary = 'templates/comment.html' if version.startswith('py.') else 'templates/index.html' if version == 'hyper152.love' else 'hyp/index.html'
        source_key = primary if primary in site['files'] else '.hyp/index.html'
        if source_key not in site['files']:
            raise ValueError(f'{version} 缺少首页')
        output_root = project / (BASE + version).lstrip('/')
        primary_output = project / site['files'][source_key]['target'].lstrip('/')
        shutil.copy2(primary_output, output_root / 'index.html')
        pages.append(('index.html', BASE + version + '/'))
        message_template = site['files'].get('templates/qiandao.html')
        if message_template:
            shutil.copy2(project / message_template['target'].lstrip('/'), output_root / 'qiandao.html')
            pages.append(('qiandao.html', BASE + version + '/qiandao.html'))
        (output_root / 'catalog.html').write_text(catalog_document(version, pages, media, len(site['messages'])), encoding='utf-8')
        report.append({'version': version, 'pages': len(pages), 'media': len(media),
                       'records': len(site['messages']),
                       'messages': sum(bool(row[1] and str(row[1]).strip()) for row in site['messages'])})
    result = {'versions': report, 'missing_references': sorted(missing)}
    (project / BASE.lstrip('/') / 'import-manifest.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', default='E:/projects/web/backup')
    parser.add_argument('--project', default=str(Path(__file__).resolve().parent.parent))
    args = parser.parse_args()
    print(json.dumps(import_sites(args.source, args.project), ensure_ascii=False, indent=2))
