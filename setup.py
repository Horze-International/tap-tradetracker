#!/usr/bin/env python

from setuptools import setup, find_packages

setup(name='tap-tradetracker',
      version="0.1.2",
      description='Singer.io tap for extracting data from the TradeTracker.com Web Service (SOAP API)',
      author='Horze',
      url='http://horze.de',
      classifiers=['Programming Language :: Python :: 3 :: Only'],
      py_modules=['tap_tradetracker'],
      install_requires=[
          'singer-python==5.9.0',
          'suds-py3==1.4.1.0',
          'pyhumps==1.6.1'
      ],
      entry_points='''
          [console_scripts]
          tap-tradetracker=tap_tradetracker:main
      ''',
      packages=find_packages(),
      package_data = {
          'tap_tradetracker': [
              'schemas/*.json',
          ],
      },
      extras_require={
          'dev': [
              'pylint',
              'ipdb',
          ]
      },
)