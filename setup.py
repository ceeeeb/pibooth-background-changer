#!/usr/bin/env python3
"""Setup script for pibooth-background-changer plugin."""

from setuptools import setup

setup(
    name='pibooth-background-changer',
    version='1.0.0',
    description='Pibooth plugin to remove and replace photo backgrounds using AI',
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    author='Christophe',
    url='https://github.com/christophe/pibooth-background-changer',
    license='MIT',
    py_modules=['pibooth_background_changer'],
    python_requires='>=3.7',
    install_requires=[
        'pibooth>=2.0.0',
        'Pillow>=8.0.0',
        'rembg>=2.0.0',
    ],
    extras_require={
        'gpu': ['rembg[gpu]>=2.0.0'],
    },
    entry_points={
        'pibooth': ['pibooth_background_changer = pibooth_background_changer'],
    },
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Plugins',
        'Intended Audience :: End Users/Desktop',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Topic :: Multimedia :: Graphics',
    ],
    keywords='pibooth photobooth background removal AI rembg',
)
