from setuptools import setup, find_packages
setup(
    name = "webkit-scraper",
    version = "0.1",
    packages = ['webkit_scraper',],
    scripts = ['webkit_service',],

    install_requires = ['rpyc',],

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
