#!/usr/bin/env python
try:
    from setuptools import setup
    with_setuptools = True
except ImportError:
    from distutils.core import setup
    with_setuptools = False

URL = 'http://hachoir.org/wiki/hachoir-parser'
CLASSIFIERS = [
    'Intended Audience :: Developers',
    'Development Status :: 5 - Production/Stable',
    'Environment :: Console :: Curses',
    'License :: OSI Approved :: GNU General Public License (GPL)',
    'Operating System :: OS Independent',
    'Natural Language :: English',
    'Programming Language :: Python']
MODULES = (
    "archive", "audio", "container", "common", "file_system", "game",
    "image", "misc", "network", "office", "program", "video")

def main():
    import hachoir_parser

    PACKAGES = {"hachoir_parser": "hachoir_parser"}
    for name in MODULES:
        PACKAGES["hachoir_parser." + name] = "hachoir_parser/" + name

    install_options = {
        "name": 'hachoir-parser',
        "version": hachoir_parser.__version__,
        "url": URL,
        "download_url": URL,
        "author": "Hachoir team (see AUTHORS file)",
        "description": "Package of Hachoir parsers used to open binary files",
        "long_description": open('README').read(),
        "classifiers": CLASSIFIERS,
        "license": 'GNU GPL v2',
        "packages": PACKAGES.keys(),
        "package_dir": PACKAGES,
    }
    if with_setuptools:
        install_options["install_requires"] = "hachoir-core>=0.7.1"
        install_options["zip_safe"] = True
    setup(**install_options)

if __name__ == "__main__":
    main()
