#!/usr/bin/env python3
"""Build a self-contained reading site from the supplied EPUB."""
import argparse
import copy
import html
import json
import posixpath
import re
import shutil
import struct
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs'
TITLE = 'Radar Countermeasures for Unmanned Aerial Vehicles'
ESC = html.escape


def plain(element):
    return re.sub(r'\s+', ' ', ''.join(element.itertext())).strip()


def local_name(tag):
    return tag.rsplit('}', 1)[-1]


def image_size(data):
    if data[:6] in (b'GIF87a', b'GIF89a'):
        return struct.unpack('<HH', data[6:10])
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return struct.unpack('>II', data[16:24])
    if data[:2] == b'\xff\xd8':
        offset = 2
        while offset + 8 < len(data):
            if data[offset] != 0xff:
                break
            while data[offset] == 0xff:
                offset += 1
            marker = data[offset]
            offset += 1
            if marker in (0xd8, 0xd9) or 0xd0 <= marker <= 0xd7:
                continue
            length = struct.unpack('>H', data[offset:offset + 2])[0]
            if marker in (0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7, 0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf):
                height, width = struct.unpack('>HH', data[offset + 3:offset + 7])
                return width, height
            offset += length
    return None


def clean(element):
    element.tag = local_name(element.tag)
    for key in list(element.attrib):
        name = local_name(key)
        if name.startswith('on') or name in ('style', 'srcdoc'):
            del element.attrib[key]
        elif key != name:
            element.attrib[name] = element.attrib.pop(key)
    for key in ('src', 'href'):
        if key in element.attrib:
            value = element.attrib[key]
            scheme = urlsplit(value).scheme.lower()
            if scheme and (key == 'src' or scheme not in ('http', 'https', 'mailto')):
                del element.attrib[key]
    for child in list(element):
        if local_name(child.tag) in ('script', 'iframe', 'object', 'embed', 'form'):
            element.remove(child)
        else:
            clean(child)
    if element.tag == 'img':
        element.set('loading', 'lazy')
        element.set('decoding', 'async')
    if element.tag == 'a' and urlsplit(element.get('href', '')).scheme:
        element.set('rel', 'noreferrer noopener')


def read_nav(node):
    return [{
        'title': plain(p.find('{*}navLabel')),
        'href': p.find('{*}content').get('src'),
        'children': read_nav(p),
    } for p in node.findall('{*}navPoint')]


def flatten(entries):
    for entry in entries:
        yield entry
        yield from flatten(entry['children'])


def nav_link(entry, prefix, current):
    active = entry['href'].split('#')[0] == current
    title = entry['title']
    match = re.match(r'^(\d+)\s+(.*)', title)
    number, label = (f'{int(match[1]):02}', match[2]) if match else ('', title)
    children = ''
    if active and entry['children']:
        children = '<ul class="subnav">' + ''.join(
            f'<li><a href="{ESC(prefix + "content/" + child["href"])}">{ESC(child["title"])}</a></li>'
            for child in entry['children']
        ) + '</ul>'
    current_attr = 'aria-current="page"' if active else ''
    return (f'<li><a class="chapter-link{" current" if active else ""}" '
            f'{current_attr} '
            f'href="{ESC(prefix + "content/" + entry["href"])}">'
            f'<span class="chapter-number">{number or "·"}</span><span>{ESC(label)}</span></a>{children}</li>')


def shell(body, title, prefix, current, nav, pager='', section_links=''):
    main_nav = [p for p in nav if p['href'].split('#')[0] not in ('xhtml/cover.html', 'xhtml/title.html', 'xhtml/copyright.html', 'xhtml/contents.html')]
    sidebar = ''.join(nav_link(p, prefix, current) for p in main_nav)
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="Read {ESC(TITLE)} with searchable chapters, original figures, and saved reading progress.">
<meta name="color-scheme" content="light dark">
<title>{ESC(title)} · Reading room</title>
<link rel="icon" href="{prefix}assets/icon.svg" type="image/svg+xml">
<link rel="stylesheet" href="{prefix}assets/reader.css">
<script src="{prefix}assets/reader.js" defer></script>
</head>
<body data-root="{prefix}" data-page="{ESC(current)}" data-title="{ESC(title)}">
<a class="skip-link" href="#main">Skip to reading</a>
<header class="topbar">
<a class="brand" href="{prefix}index.html"><span class="brand-mark" aria-hidden="true">r.</span><span>Reading room</span></a>
<span class="topbar-label">RADAR &amp; SENSING / 01</span>
<div class="toolbar">
<button class="search-trigger" type="button" data-search>Search book <kbd>⌘ K</kbd></button>
<button class="theme-toggle" type="button" aria-label="Use dark theme" title="Switch theme">◐</button>
<button class="menu-toggle" type="button" aria-controls="sidebar" aria-expanded="false">Contents</button>
</div></header>
<aside id="sidebar" class="sidebar" aria-label="Book navigation">
<div class="sidebar-heading"><span class="eyebrow">THE BOOK</span><h2>Radar Countermeasures<br><span>for Unmanned Aerial Vehicles</span></h2></div>
<a class="overview-link" href="{prefix}index.html">Overview <span aria-hidden="true">↗</span></a>
<p class="nav-label">CONTENTS</p><nav aria-label="Chapters"><ul class="chapter-list">{sidebar}</ul></nav>
<div class="sidebar-footer"><a href="{prefix}downloads/radar-countermeasures.epub" download>Download EPUB <span aria-hidden="true">↓</span></a><span>Original edition · 2021</span></div>
</aside>
<main id="main" class="main {'overview' if not current else 'reading'}" tabindex="-1">
{body}{pager}
<footer class="page-footer"><span>Radar &amp; sensing</span><a href="{prefix}content/xhtml/copyright.html">Publication details</a><a href="#main">Back to top ↑</a></footer>
</main>
{section_links}
<dialog class="search-dialog" aria-labelledby="search-title">
<div class="search-heading"><h2 id="search-title">Search the book</h2><button type="button" class="close-search" aria-label="Close search">×</button></div>
<label for="book-query" class="sr-only">Search terms</label><input id="book-query" type="search" placeholder="A topic, phrase, or equation reference…" autocomplete="off">
<p class="search-status" role="status">Search across all chapters and sections.</p><div class="search-results"></div>
</dialog>
</body></html>'''


def build(epub):
    OUT.mkdir(exist_ok=True)
    (OUT / 'assets').mkdir(exist_ok=True)
    (OUT / 'downloads').mkdir(exist_ok=True)
    download = OUT / 'downloads/radar-countermeasures.epub'
    if epub.resolve() != download.resolve():
        shutil.copyfile(epub, download)
    for name in ('reader.css', 'reader.js', 'icon.svg'):
        shutil.copyfile(ROOT / 'reader' / name, OUT / 'assets' / name)
    (OUT / '.nojekyll').write_text('')
    search = []
    with zipfile.ZipFile(epub) as archive:
        container = ET.fromstring(archive.read('META-INF/container.xml'))
        package_path = container.find('.//{*}rootfile').get('full-path')
        package_dir = posixpath.dirname(package_path)
        package = ET.fromstring(archive.read(package_path))
        manifest = {item.get('id'): item.attrib for item in package.find('{*}manifest')}
        spine = [manifest[item.get('idref')]['href'] for item in package.find('{*}spine')]
        ncx = next(item['href'] for item in manifest.values() if item.get('media-type') == 'application/x-dtbncx+xml')
        nav = read_nav(ET.fromstring(archive.read(f'{package_dir}/{ncx}')).find('{*}navMap'))
        titles = {item['href'].split('#')[0]: item['title'] for item in reversed(list(flatten(nav)))}
        pages = {}
        for path in spine:
            document = ET.fromstring(archive.read(f'{package_dir}/{path}'))
            body = document.find('{*}body')
            body = copy.deepcopy(body)
            clean(body)
            for image in body.iter('img'):
                source = posixpath.normpath(posixpath.join(package_dir, posixpath.dirname(path), image.get('src', '')))
                if source in archive.namelist():
                    size = image_size(archive.read(source))
                    if size:
                        image.set('width', str(size[0]))
                        image.set('height', str(size[1]))
            pages[path] = body
        for name in archive.namelist():
            if not name.startswith(package_dir + '/') or name.endswith('/'):
                continue
            relative = PurePosixPath(name).relative_to(package_dir)
            if '..' in relative.parts or relative.suffix.lower() not in ('.jpg', '.jpeg', '.png', '.gif', '.svg', '.woff', '.woff2', '.ttf'):
                continue
            target = OUT / 'content' / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(name))
        for position, path in enumerate(spine):
            body = pages[path]
            title = titles.get(path) or plain(body.find('.//h1') if body.find('.//h1') is not None else body)[:100]
            if path == 'xhtml/half.html': title = 'Half title'
            if path == 'xhtml/abstract.html': title = 'Abstract'
            # Keep all original identifiers, figure references, and relative links.
            paragraphs = []
            section_title, section_id = title, ''
            def flush():
                if paragraphs:
                    search.append({'title': section_title, 'chapter': title, 'href': 'content/' + path + ('#' + section_id if section_id else ''), 'text': ' '.join(paragraphs)})
                    paragraphs.clear()
            for element in body.iter():
                if re.fullmatch(r'h[1-6]', element.tag):
                    flush()
                    section_title = plain(element)
                    section_id = element.get('id', '')
                elif element.tag in ('p', 'li', 'td', 'th'):
                    paragraphs.append(plain(element))
            flush()
            for heading in body.iter():
                if heading.tag in ('h1', 'h2'):
                    heading.tag = 'h1'
                    break
            if not any(element.tag == 'h1' for element in body.iter()):
                heading = ET.Element('h1', {'class': 'sr-only'})
                heading.text = title
                body.insert(0, heading)
            contents = ''.join(ET.tostring(child, encoding='unicode', method='html') for child in body)
            # Wide tables scroll within the text column on small screens.
            contents = re.sub(r'(<table\b.*?</table>)', r'<div class="table-scroll" tabindex="0" role="region" aria-label="Data table">\1</div>', contents, flags=re.S)
            word_count = len(re.findall(r'\b\w+\b', plain(body)))
            minutes = max(1, round(word_count / 150))
            meta = f'<div class="reading-meta"><a href="../../index.html">The book</a><span>/</span><span>{minutes} min read</span><div class="font-controls" aria-label="Text size"><button type="button" data-font="-1" aria-label="Decrease text size">A−</button><button type="button" data-font="1" aria-label="Increase text size">A+</button></div></div>'
            progress = '<div class="reading-progress" aria-hidden="true"><span></span></div>'
            content = f'{progress}{meta}<article class="book-text">{contents}</article>'
            prev = spine[position - 1] if position else None
            nxt = spine[position + 1] if position + 1 < len(spine) else None
            links = []
            for label, target, arrow in [('Previous', prev, '←'), ('Next', nxt, '→')]:
                if target:
                    links.append(f'<a class="pager-{label.lower()}" href="{ESC(posixpath.basename(target))}"><small>{label} {arrow}</small><span>{ESC(titles.get(target, "Front matter"))}</span></a>')
            pager = '<nav class="pager" aria-label="Reading order">' + ''.join(links) + '</nav>'
            headings = [e for e in body.iter() if e.tag == 'h3' and e.get('id')]
            sections = '<aside class="on-this-page" aria-label="On this page"><span class="eyebrow">ON THIS PAGE</span>' + ''.join(f'<a href="#{ESC(e.get("id"))}">{ESC(plain(e))}</a>' for e in headings) + '</aside>' if headings else ''
            target = OUT / 'content' / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(shell(content, title, '../../', path, nav, pager, sections), encoding='utf-8')

        chapters = [p for p in nav if re.match(r'^\d+ ', p['title'])]
        rows = []
        for chapter in chapters:
            number, name = chapter['title'].split(' ', 1)
            rows.append(f'<a class="chapter-row" href="content/{ESC(chapter["href"])}"><span class="row-number">{int(number):02}</span><span>{ESC(name)}</span><span class="row-arrow" aria-hidden="true">↗</span></a>')
        home = f'''<section class="book-intro">
<div class="eyebrow"><span class="status-dot"></span> ENGINEERING COLLECTION <span class="edition">2021 EDITION</span></div>
<h1>Radar Countermeasures<br><span>for Unmanned<br>Aerial Vehicles</span></h1>
<p class="editors">Edited by Carmine Clemente, Francesco Fioranelli,<br>Fabiola Colone, and Gang Li</p>
<p class="book-description">A technical reference on radar sensing, detection, tracking, and classification of unmanned aerial vehicles.</p>
<div class="intro-actions"><a class="primary-action" id="start-reading" href="content/xhtml/Chapter.html#c00">Start reading <span aria-hidden="true">→</span></a><a class="download-link" href="downloads/radar-countermeasures.epub" download>Download EPUB ↓</a></div>
<div class="book-stats"><div><strong>12</strong><span>chapters</span></div><div><strong>15–25 h</strong><span>careful reading · estimate</span></div><div><strong>30–50 h</strong><span>with notes · estimate</span></div></div>
</section>
<section class="contents-section" aria-labelledby="contents-title"><div class="section-title"><h2 id="contents-title">Inside the book</h2><span>12 CHAPTERS + INTRODUCTION</span></div>
<a class="introduction-row" href="content/xhtml/Chapter.html#c00"><span>Introduction</span><span aria-hidden="true">↗</span></a>
{''.join(rows)}
<a class="introduction-row end-row" href="content/xhtml/Conclusion.html"><span>Conclusion</span><span aria-hidden="true">↗</span></a>
</section>'''
        (OUT / 'index.html').write_text(shell(home, TITLE, './', '', nav), encoding='utf-8')
    (OUT / 'assets/search-index.json').write_text(json.dumps(search, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print(f'Built {len(spine)} reading pages, {len(search)} searchable sections, and the overview.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('epub', type=Path, nargs='?', default=OUT / 'downloads/radar-countermeasures.epub')
    build(parser.parse_args().epub)
