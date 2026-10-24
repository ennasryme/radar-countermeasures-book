# Radar Countermeasures — reading room

[Read the book online](https://ennasryme.github.io/radar-countermeasures-book/).

A static browser reader built from the supplied EPUB. It includes the original chapters and illustrations, section search, adjustable text, light and dark themes, and a reading position saved in the browser.

Build with the standard Python library:

```sh
python3 scripts/build_reader.py /path/to/book.epub
```

Rebuild from the included download:

```sh
python3 scripts/build_reader.py
```

Preview locally:

```sh
python3 -m http.server 8765 --directory docs
```

The `docs` directory is the complete static site and can be served at a subdirectory. The original EPUB is retained in `docs/downloads`. Reading position and preferences stay in each browser. Publication credits and rights statements remain part of the book.
