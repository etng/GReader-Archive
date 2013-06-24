#!/bin/env python
import logging
import sys
import os
import httplib, urllib
import random
import socket
import time
from StringIO import StringIO
import gzip
import getpass
import ConfigParser
try:
    import json
except ImportError:
    import simplejson as json

logging.basicConfig(format='%(asctime)s [%(levelname)s] %(message)s')
logging.getLogger().setLevel(logging.INFO)
#logging.getLogger().setLevel(logging.DEBUG)

class GRRequester:
    servers = ["www.google.com"]
    conn = None
    # Enabling gzip saves as much as 60% of downloading time.
    # user-agent is (strangely) required otherwise gzip will not be enabled
    commonheader = {"Host": "www.google.com", 'Accept-Encoding': 'gzip',
        'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; rv:20.0) Gecko/20100101 Firefox/20.0'}
    user = None
    pwd = None
    auth = None

    def setServers(self, serverlist):
        if not isinstance(serverlist, (list, tuple)):
            logging.error("GRRequester.setServers(): Invalid parameter")
            return 1
        self.servers = serverlist
    def setUserAgent(self, ua):
        self.commonheader["User-Agent"] = ua
    def setWaitTime(self, waittime):
        self.waittime = waittime
    # perfoem a request to Google server
    def request(self, path, postdata, tries, useauth = True):
        status = 0
        data = ""
        params = None
        headers = self.commonheader
        if postdata is not None:
            params = urllib.urlencode(postdata)
            headers['Content-type'] = 'application/x-www-form-urlencoded'
        if useauth:
            headers['Authorization'] = 'GoogleLogin auth=' + self.auth
        for i in range(tries):  # retry on network errors
            try:
                if self.conn is None:
                    self.reconnect()
                if postdata is not None:
                    self.conn.request("POST", path, params, headers)
                else:
                    self.conn.request("GET", path, headers = headers)
                response = self.conn.getresponse()
                status = response.status
                data = response.read()
                if response.getheader('Content-Encoding') == 'gzip':
                    data = gzip.GzipFile(fileobj=StringIO(data)).read()
            except socket.error, e:
                logging.error("Network error: %s" % (e))
                if self.conn is not None:
                    self.conn.close()
                    self.conn = None
                time.sleep(self.waittime)
                continue
            except httplib.BadStatusLine, e:
                logging.error("Network error (BadStatusLine): %s" % (e))
                if self.conn is not None:
                    self.conn.close()
                    self.conn = None
                time.sleep(self.waittime)
                continue
            if status == 503:   # antispidered!
                logging.info('Client IP antispidered. wait 1 hour and continue...')
                logging.debug(data)
                time.sleep(3600)
                self.reconnect()
                self.setUser(self.user, self.pwd)   # try relogin
                continue
            break   # should be no exception if arrived here
        return status, data

    def reconnect(self):
        if self.conn is not None:
            self.conn.close()
            self.conn = None
        self.conn = httplib.HTTPSConnection(self.servers[random.randint(0, len(self.servers) - 1)], timeout = 30)

    def setUser(self, user, pwd):
        self.auth = None
        status, data = self.request('/accounts/ClientLogin',
            {'Email': user, 'Passwd': pwd, 'service': 'reader', 'accountType': 'HOSTED_OR_GOOGLE'}, 99, False)
        if status != 200 and status != 503:
            logging.error("Login failed. please check network and verify email and/or password")
            self.user = self.pwd = None
            return -1
        for param in data.splitlines():
            if param.startswith('Auth='):
                self.auth = param[5:]   # skip 'Auth='
                logging.debug('Auth: %s' % (self.auth))
        if self.auth is None:   # auth not found, treat as a failure
            logging.error("Auth not found. please verify email and/or password")
            self.user = self.pwd = None
            return -1
        self.user = user
        self.pwd = pwd
        return 0

    def relogin(self):
        if self.user is not None and self.pwd is not None:
            self.setUser(self.user, self.pwd)

    def __del__(self):
        if self.conn is not None:
            self.conn.close()

#end of class GRRequester

def fileWrite(filename, content):
    with open(filename, 'w') as f:
        f.write(content)
def gzFileWrite(filename, content):
    with gzip.open(filename, 'wb') as f:
        f.write(content)

def fileRead(filename):
    try:
        with open(filename) as f:
            return f.read()
    except IOError:
        return ''

def gzFileRead(filename):
    try:
        with gzip.open(filename, 'rb') as f:
            return f.read()
    except IOError:
        return ''
# encode certain chars in  RSS url so that it can be properly interpreted
def urlReplace(url):    # '%' must be replaced at first place
    return url.replace('%', '%25').replace('?', '%3F').replace('&', '%26').replace('=', '%3d')

# clean certain chars in string so that it conforms to valid file/dir naming rules
def dirnameClean(dirname):
    spechars = '/\\?*"<>|:.'
    for char in spechars:
        dirname = dirname.replace(char, '_')
    return dirname
def extractTag(content, tagname):
    open_tag = '<%s>' % tagname
    close_tag = '</%s>' % tagname
    cb = content.find(open_tag)
    if cb<0:
        return False
    ce = content.find(close_tag, cb+1)
    if ce<0:
        return False
    return content[cb+len(open_tag) : ce]

def mkdir(dirname):
    if not os.path.exists(dirname):
        os.makedirs(dirname)
def touch(path):
    with open(path, 'a'):
        os.utime(path, None)
def processWrite(filename, fin, idx, name):
    with open(filename, 'w') as f:
        f.write("%d\n%d\n%s\n" % (fin, idx, name))

def processRead(filename):
    try:
        with open(filename) as f:
            fin = int(f.readline())
            idx = int(f.readline())
            name = f.readline().rstrip()
    except IOError:
        return None, None, None
    return fin, idx, name

def main():
    logging.info("Start")

    config = ConfigParser.RawConfigParser()
    config.read('config.ini')

    requester = GRRequester()

    # Try to load custom IPs
    servers = []
    for ip in config.get('request', 'customip').split('\n'):
        ip = ip.strip()
        if ip != '':
            servers.append(ip)
    if len(servers) > 0:
        logging.warning("Loaded %d custom Google IPs from config.ini, Remove that file if you experience download failure"
            % (len(servers)))
        requester.setServers(servers)
    ua =config.get('request', 'User-Agent')
    if ua is not None:
        request.setUserAgent(ua)


    # Ask for username and password
    print "\nIf your Google account uses 2-step verification, please refer to http://live.aulddays.com/tech/13/google-reader-archive-download.htm#advanced"
    user = config.get('account', 'user', None)
    if user is None:
        user = raw_input("Google Reader Username: ")
        logging.debug(user)
    pwd = config.get('account', 'pwd', None)
    if pwd is None:
        os.system("stty -echo")
        pwd = raw_input("Password (will not display while typing): ")
        os.system("stty echo")
        pwd = getpass.getpass("Password (will not display while typing): ")
        logging.debug(pwd)

    if requester.setUser(user, pwd) != 0:
        logging.error("")
        exit(1)

    datadir = config.get('general', 'datadir', 'data')
    mkdir(datadir)
    userdir = datadir + '/' + user
    mkdir(userdir)
    waittime = config.get('general', 'waittime')
    gfin, gNone, gid = processRead(userdir + '/process.dat')
    if gfin is not None:    # have process record
        if gfin != 0: # already finished
            overwrite = config.get('general', 'overwrite_on_success', None)
            if overwrite is None:
                overwrite = raw_input("%s's data has already finished downloading. Start over again? (y/n): " % (user))
            if not (overwrite.startswith('y') or overwrite.startswith('Y') or
                overwrite.startswith('t') or overwrite.startswith('T') or overwrite.startswith('1')):
                    logging.info("Finish")
                    exit(0)
            gfin = gid = None
        elif len(gid) > 0:  # partial download found
            while 1:
                overwrite = config.get('general', 'overwrite_on_partial', None)
                if overwrite is None:
                    overwrite = raw_input("%s's data has already finished downloading. Start over again? (y/n): " % (user))
                if overwrite.lower().startswith('s'):
                    gfin = gid = None
                    break
                elif overwrite.lower().startswith('c'): # continue
                    try:
                        subs = json.loads(gzFileRead(userdir + '/subscriptions.json.gz'))
                        if not subs.has_key('subscriptions'):
                            raise ValueError
                        break
                    except ValueError:
                        logging.error("Invalid unfinished download data. Please delete all downloaded data and try again.")
                        exit(1)
        else: # gfin != 0 and len(gid) == 0, invalid data load
            gfin = gid = None
    subscribtions_url = 'https://www.google.com/reader/api/0/subscription/list?output=json'
    if gfin is None:
        logging.info('Retrieving subscribtion list...')
        for i in range(3):
            status, data = requester.request(subscribtions_url, None, 3)
            if status == 200:
                subs = json.loads(data)
                if subs.has_key('subscriptions'):
                    break
            logging.info('%d: %s' % (status, data))
            time.sleep(waittime)
        if status != 200:
            logging.error("Error retrieving subscription list")
            sys.exit(1)
        logging.info('Retrieved %d items of user %s' % (len(subs['subscriptions']), user))
        gzFileWrite(userdir + '/subscriptions.json.gz', data)

    # download each subscription
    for sub in subs['subscriptions']:
        logging.info("Processing %s (%s)..." % (sub['title'], sub['id']))
        if gid != None and sub['id'] != gid:
            print gid, sub['id']
            logging.info('Already downloaded, skip')
            continue
        elif gid is None:
            processWrite(userdir + '/process.dat', 0, 0, sub['id'])

        # determin the dir(s) to put this subscription
        for cat in sub['categories']:
            catdir = userdir + '/category/' + dirnameClean(cat['label'])
            mkdir(catdir)
            subdir = catdir + '/' + urllib.quote_plus(sub['id'])
            #subdir = catdir + '/' + dirnameClean(sub['title'])
            touch(subdir)
        maybe_subscription_dir = subscription_dir = userdir + '/feed/' + urllib.quote_plus(sub['id'])
        #maybe_subscription_dir = subscription_dir = userdir + '/feed/' + dirnameClean(sub['title'])
        # check meta info in case of subscriptions having the same name
        idx = 0
        while 1:
            mkdir(maybe_subscription_dir)
            try:
                meta = json.loads(gzFileRead(maybe_subscription_dir + '/meta.json.gz'))
            except ValueError:
                meta = None
            if meta is not None and meta.has_key('id'):
                if meta['id'] == sub['id']: # right one
                    subscription_dir = maybe_subscription_dir
                    break
                else:   # not the right one, try next dir
                    idx += 1
                    maybe_subscription_dir = subscription_dir + "_%d" % (idx)
                    continue
            else:   # meta not found, write current
                gzFileWrite(subscription_dir + '/meta.json.gz', json.dumps(sub))
                break
        #end of determin the dir(s) to put this subscription

        # download contents
        c = ''  # c param in url
        idx = 0
        if gid != None and sub['id'] == gid:    # subscription partially downloaded
            gid = None
            sfin, idx, c = processRead(subscription_dir + '/process.dat')
            if sfin is not None and sfin != 0:  # finished
                logging.info('Already downloaded, skip')
                continue
            elif sfin is None or c == '':   # none downloaded or invalid data, start over again
                c = ''
                idx = 0
        while 1: # download each file of this subscription
            url = 'https://www.google.com/reader/atom/' + urlReplace(sub['id']) + '?n=2000'
            if c != '':
                url += '&c=' + c
            logging.info("downloading %s to %05d.xml" % (url, idx))
            status, data = requester.request(url, None, 99999)
            if status != 200:
                logging.error("Error downloading")
                logging.debug("%d: %s" % (status, data))
                logging.error("Give up this subscription")
                time.sleep(waittime)
                break
            gzFileWrite(subscription_dir + "/%05d.xml.gz" % (idx), data)
            idx += 1
            sfin = 0

            c = extractTag(data, 'gr:continuation')
            if c == False:
                sfin=1
                logging.info("Finished %s (%s). %d files downloaded" % (sub['title'], sub['id'], idx))
            elif c == '':
                sfin=1
                logging.info("Finished %s (%s). %d files downloaded" % (sub['title'], sub['id'], idx))
            processWrite(subscription_dir + '/process.dat', sfin, idx, c)
            logging.info("Fin and sleep")
            time.sleep(waittime)
            if sfin:
                break
        # end of while 1: # download each file of this subscription
    # end of download each subscription
    processWrite(userdir + '/process.dat', 1, 0, '')
    logging.info("%s finished downloading", user)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print
        logging.info("Exit. You may choose to continue unfinished download next time.")

