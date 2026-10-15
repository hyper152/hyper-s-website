from contextlib import closing
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest

from src.import_legacy_sites import VERSIONS, import_sites, BASE, MEDIA_BASE


class LegacySiteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.sources = self.root / 'backups'
        self.project = self.root / 'site'
        self.web = self.project / 'pages/projects/web'
        self.web.mkdir(parents=True)
        (self.web / 'index.html').write_text('现有开发日志不能覆盖', encoding='utf-8')
        for version in VERSIONS:
            source = self.sources / version
            (source / 'templates').mkdir(parents=True)
            (source / 'data').mkdir()
            (source / 'templates/comment.html').write_text(
                '<html><head><style>body {display:flex}</style></head><body><div class="login-container">'
                '<form action="/login" method="post"><input name="name"><button type="submit">签到</button>'
                '</form></div></body></html>', encoding='utf-8')
            (source / 'templates/qiandao.html').write_text(
                '<body><meta http-equiv="refresh" content="60"></body><h2>{{name}}，留言成功</h2>'
                '{% for i in data[::-1] %}{{i[0]}} {{i[1]}}<br>{% endfor %}', encoding='utf-8')
            (source / 'templates/index.html').write_text('<div>爱心首页</div>', encoding='utf-8')
            with closing(sqlite3.connect(source / 'data/data.db')) as db:
                db.execute('CREATE TABLE students(name TEXT,classid TEXT)')
                db.executemany('INSERT INTO students VALUES (?,?)', [('<script>bad</script>', '旧留言'), (None, None)])
                db.commit()
            (source / 'web.py').write_text('PRIVATE_BACKEND', encoding='utf-8')
            (source / 'settings.php').write_text('PRIVATE_SECRET', encoding='utf-8')
            (source / 'private.htm').write_text('<?php echo "secret"; ?>', encoding='utf-8')
            home = source / ('hyp' if version == 'hyper152.cn' else '.hyp')
            home.mkdir()
            (home / 'index.html').write_text(
                '<head><link href="main.css" rel="stylesheet"></head><body>'
                '<img src="photo.jpg"><a href="http://py.hyper152.love/">旧留言</a></body>', encoding='utf-8')
            (home / 'photo.jpg').write_bytes(b'original-image-bytes')
            (home / 'main.css').write_text('body {background:url(photo.jpg)}', encoding='utf-8')

    def tearDown(self):
        self.temp.cleanup()

    def test_static_archive_preserves_source_database_and_existing_web_page(self):
        paths = list(self.sources.rglob('*'))
        original = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths if path.is_file()}
        result = import_sites(self.sources, self.project)
        self.assertEqual(result['missing_references'], [])
        self.assertEqual((self.web / 'index.html').read_text(encoding='utf-8'), '现有开发日志不能覆盖')
        for path, digest in original.items():
            self.assertEqual(hashlib.sha256(Path(path).read_bytes()).hexdigest(), digest)
        for version in VERSIONS:
            self.assertTrue((self.web / version / 'index.html').is_file())
            self.assertTrue((self.web / version / 'catalog.html').is_file())
            self.assertFalse((self.web / version / 'web.py').exists())
            self.assertFalse((self.web / version / 'settings.php').exists())
            self.assertFalse((self.web / version / 'data/data.db').exists())
            self.assertFalse((self.web / version / 'private.htm').exists())

    def test_history_is_escaped_and_form_cannot_write_to_old_login_route(self):
        result = import_sites(self.sources, self.project)
        version = VERSIONS[0]
        history = (self.web / version / 'qiandao.html').read_text(encoding='utf-8')
        self.assertIn('&lt;script&gt;bad&lt;/script&gt;', history)
        self.assertIn('旧留言', history)
        self.assertIn('历史留言（只读）', history)
        self.assertNotIn('http-equiv="refresh"', history)
        page = (self.web / version / 'index.html').read_text(encoding='utf-8')
        self.assertIn('method="get"', page)
        self.assertIn('disabled', page)
        self.assertIn(BASE + version + '/qiandao.html', page)
        self.assertIn('← 返回上一页', page)
        self.assertIn('⌂ 首页', page)
        self.assertEqual(result['versions'][0]['records'], 2)
        self.assertEqual(result['versions'][0]['messages'], 1)

    def test_renamed_hidden_paths_and_cross_version_links_use_local_archives(self):
        import_sites(self.sources, self.project)
        version = 'hyper152.love'
        content = (self.web / version / 'hyp/index.html').read_text(encoding='utf-8')
        self.assertIn(BASE + 'py.hyper152.love/', content)
        self.assertIn(MEDIA_BASE + version + '/hyp/photo.jpg', content)
        css = (self.web / version / 'hyp/main.css').read_text(encoding='utf-8')
        self.assertIn(MEDIA_BASE + version + '/hyp/photo.jpg', css)
        media = self.project / 'media/pages/projects/web' / version / 'hyp/photo.jpg'
        self.assertEqual(media.read_bytes(), b'original-image-bytes')

    def test_missing_assets_are_reported_instead_of_invented(self):
        source = self.sources / VERSIONS[0] / 'templates/comment.html'
        source.write_text('<img src="missing.jpg">', encoding='utf-8')
        result = import_sites(self.sources, self.project)
        self.assertIn((VERSIONS[0], 'templates/comment.html', 'missing.jpg'), result['missing_references'])
