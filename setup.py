#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
from io import open
import os.path as osp
from setuptools import setup


HERE = osp.abspath(osp.dirname(__file__))

# Read version from module without importing it
with open(osp.join(HERE, 'pibooth_background_changer.py'), encoding='utf-8') as f:
    version = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', f.read()).group(1)

setup(
    name='pibooth_background_changer',
    version=version,
    description="Pibooth plugin to remove and replace photo backgrounds using AI",
    long_description=open(osp.join(HERE, 'README.md'), encoding='utf-8').read(),
    long_description_content_type='text/markdown',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Plugins',
        'Intended Audience :: End Users/Desktop',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3',
        'Topic :: Multimedia :: Graphics',
    ],
    author="Christophe",
    url="https://github.com/ceeeeb/pibooth-background-changer",
    license='MIT',
    keywords=['pibooth', 'photobooth', 'background', 'removal', 'AI', 'rembg'],
    py_modules=['pibooth_background_changer'],
    python_requires=">=3.7",
    install_requires=[
        'Pillow>=8.0.0',
        'pibooth>=2.0.0',
        'rembg[cpu]>=2.0.0',
    ],
    extras_require={'gpu': ['rembg[gpu]>=2.0.0']},
    zip_safe=False,
    entry_points={'pibooth': ["pibooth_background_changer = pibooth_background_changer"]},
)
