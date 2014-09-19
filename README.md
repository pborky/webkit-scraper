# Overview

**Author:** Peter Boraros (based on Niklas Baumstark's webkit-server)

A standalone version of the Webkit server included in [capybara-webkit][1].
It is rewritten by pborky with PySide QT bindings and the following improvements over the
original version from thoughtbot:

* `Wait` command to wait for the current page to load
* `SetAttribute` command to [configure certain `QWebkit` settings][2]
* `SetHtml` command to [load custom HTML][3] into the browser (e.g. to
  execute scripts on web pages scraped by a static scraper)
* `SetViewportSize` command to set the viewport size of the in-memory browser

If you are interested in web scraping using this server, have a look at [dryscrape][4].

# Building and Installing

It is recomended to used distribution version of PySide, e.g. for Ubuntu you should install 
at least `python-pyside.qtwebkit` package. Then 
invoke `pip install --process-dependency-links git+https://github.com/pborky/webkit-scraper.git` to install the server.

# Contact, Bugs, Contributions

If you have any problems with this software, don't hesitate to open an 
issue on [Github](https://github.com/pborky/webkit-scraper) or open a pull 
request.

# License

This software is based on [capybara-webkit][1].
capybara-webkit is Copyright (c) 2011 thoughtbot, inc. It is free software, and
may be redistributed under the terms specified in the LICENSE file.

 [1]: https://github.com/thoughtbot/capybara-webkit
 [2]: https://github.com/thoughtbot/capybara-webkit/pull/171
 [3]: https://github.com/thoughtbot/capybara-webkit/pull/170
 [4]: https://github.com/niklasb/dryscrape
