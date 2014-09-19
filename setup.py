from setuptools import setup, find_packages
setup(
    name = "webkit-scraper",
    version = "0.1",
    packages = ['webkit_scraper',],
    scripts = ['webkit_service',],

    install_requires = [
        'rpyc', 
        'psutil', 
        'dryscrape==0.8',
      ],

    dependency_links = [
        'git+https://github.com/pborky/dryscrape.git#egg=dryscrape-0.8',
      ],

    package_data = {
          '': ['*.js',],
        },

    author = "pBorky",
    author_email = "pborky@gmail.com",
    description = "a Webkit-based, headless browser instance",
    license = "MIT",
    keywords = "hello world example examples",
    url = "https://github.com/pborky/webkit-scraper",
)
