"""
This is pythonic implementation of webkit-server using PyQt4.
Based on https://github.com/niklasb/webkit-server
"""

import rpyc
import time
from webkit_scraper.driver import Driver
conn = rpyc.connect('localhost', 18811)
host = conn.root.discover('WEBKIT')
if host is None:
  print 'Failed to discover WEBKIT service.'
  exit(1)
conn = rpyc.connect(*host)
c = Driver(conn)
USER_AGENT = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chromium/28.0.1500.71 Chrome/28.0.1500.71 '
ACCEPT_LANG = 'en-US,en;q=0.8'
ACCEPT = 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
c.set_header('user-agent',USER_AGENT)
c.set_header('accept-language', ACCEPT_LANG)
c.set_header('accept', ACCEPT)
c.set_error_tolerant(True)
c.set_attribute('auto_load_images', False)
c.set_attribute('plugins_enabled', False)
c.clear_cookies()
c.visit('http://search.yahoo.com/')
c.wait()
n = c.at_xpath('//input[@name="p"]')
n.set('"4FA" buy')
f = n.form()
f.submit()
for i in range(5):
  print '\n'.join('%s (%s)' %(n.text(), n.get_attr('href')) for n in c.xpath('//ol/li//h3/a'))
  n = c.at_xpath('//div[@id="pg"]/a[@id="pg-next"]')
  n.click()
