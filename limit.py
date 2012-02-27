#-*- coding: utf-8 -*-
"""

Module for warning mailing list members when they reach a daily limit
of mails.

Copyright (C) 2012 Nikola Škorić (nskoric [ at ] gmail.com)

This program is free software; you can redistribute it and/or
modify it under the terms of the GNU General Public License
as published by the Free Software Foundation; either version 2
of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.

Please see the GPL license at http://www.gnu.org/licenses/gpl.txt

To contact the author, see http://github.com/dijxtra/list-limit
"""
import imaplib, collections, ConfigParser, pickle, sys, smtplib, logging
from datetime import time, timedelta, datetime
from time import mktime
from email.mime.text import MIMEText
from email.utils import parseaddr, parsedate
from os.path import exists
from string import Template

def parse_conf(conf_file = "limit.conf"):
    Config = ConfigParser.ConfigParser()
    Config.read(conf_file)
    account = dict(Config.items('Account'))
    outgoing = dict(Config.items('Outgoing'))
    limits = dict(Config.items('Limits'))
    exceptions = dict(Config.items('Exceptions'))

    try:
        account['list'] = Config.get('Account', 'list')
    except ConfigParser.NoOptionError:
        account['list'] =''
    try:
        limits['warned_file'] = Config.get('Limits', 'warned_file')
    except ConfigParser.NoOptionError:
        limits['warned_file'] ='warned.p'

    return account, outgoing, limits, exceptions

def mock_get_author_freqs(account, start):
    return {'nskoric@gmail.com' : 3, 'burek@pita.net' : 4, 'john@microsoft.com' : 1, 'mike@microsoft.com' : 5}

def get_author_freqs(account, start):
    """Connect to IMAP mail server, retreive mails and create dictionary of author frequencies.

    Arguments:
    server, port, username, password -- obvious
    list -- address of mailing list in question as it would appear in RFC2822 To: filed
    start -- start of current cycle: we count emails sent after this moment in time
    """
    M = imaplib.IMAP4_SSL(account['host'], int(account['port']))
    M.login(account['username'], account['password'])
    M.select()
    typ, data = M.search(None, '(SENTSINCE {date})'.format(date=start.strftime("%d-%b-%Y"))) #fetching emails sent after midnight (IMAP can search only by date, not by time)

    freq = collections.defaultdict(int)
    for num in data[0].split(): #for each email
        typ, from_data = M.fetch(num, '(BODY[HEADER.FIELDS (FROM)])')
        typ, to_data = M.fetch(num, '(BODY[HEADER.FIELDS (TO)])')
        typ, date_data = M.fetch(num, '(BODY[HEADER.FIELDS (DATE)])')

        #parse RFC2822 headers
        mail = parseaddr(from_data[0][1])[1]
        to = parseaddr(to_data[0][1])[1]
        date = date_data[0][1]

        #check if this email was sent to the list in current cycle
        if (account['list'] == to or account['list'] == '') and in_this_cycle(date, start):
            freq[mail] += 1

    M.close()
    M.logout()

    return freq

def extract_offenders(freqs, limit):
    """Return list of authors who sent equal or more mails than allowed."""
    offenders = []
    for m, f in freqs.items():
        if f >= limit:
            offenders.append(m)

    return offenders

def get_start_time(hours):
    """Return datetime object which represents given number of hours after start of current day."""
    td = timedelta(0, 0, 0, 0, 0, hours)
    d = datetime.today()
    midnight = datetime.combine(d, time())

    return (midnight + td)

def in_this_cycle(date, start):
    """Check if RFC2822 Date header string represents time after start of current cycle

    Arguments:
    date -- RFC2822 Date header
    start -- start of current cycle"""
    if date.startswith("Date:"):
        date = date[5:]

    date = parsedate(date)

    return mktime(date) > mktime(start.timetuple())

def get_offenders(account, limits):
    """Return list of emails offending the "number of mails daily" limit on a given mailing list.
"""
    start_time = get_start_time(int(limits['start_hour']))
    
#    freqs = mock_get_author_freqs(account, start_time)
    freqs = get_author_freqs(account, start_time)

#    print_leaderboard(freqs)

    offenders = extract_offenders(freqs, int(limits['count']))
    
    return offenders

def print_leaderboard(freqs):
    """Print to the STDOUT list of authors with their current mail-count"""
    print "Leaderboard:"
    for f in sorted(freqs, key=freqs.get, reverse=True):
        print f, freqs[f]

def cleanup_already_warned(offenders, warned_file):
    if not exists(warned_file):
        pickle.dump([], open(warned_file, "wb" ))
        return

    already_warned = pickle.load(open(warned_file, "rb"))

    not_offending = []
    for w in already_warned:
        if w not in offenders:
            not_offending.append(w)

    if not not_offending: # list is empty
        return

    for n in not_offending:
        already_warned.remove(n)

    pickle.dump(already_warned, open(warned_file, "wb" ))

    return

def remove_already_warned(offenders, warned_file):
    if not exists(warned_file):
        pickle.dump([], open(warned_file, "wb" ))
        already_warned = []
    else:
        already_warned = pickle.load(open(warned_file, "rb"))
        logging.debug("Already warned: {0}".format(already_warned))

    for w in already_warned:
        offenders.remove(w.strip())

    return offenders

def send_email(to, subject, body, outgoing, exceptions = None):
    if exceptions is not None:
        if to in exceptions['blacklist']:
            return

        if exceptions['whitelist'] and not to in exceptions['whitelist']:
            return

    logging.info("Sending {subject} to {email}.".format(subject, to))

    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = outgoing['email']
    msg['To'] = to

    s = smtplib.SMTP(outgoing['host'] + ':' + outgoing['port'])
    s.login(outgoing['username'], outgoing['password'])
    s.starttls()
    s.sendmail(outgoing['email'], [to], msg.as_string())
    s.quit()

def parse_exceptions(exceptions):
    whitelist = []
    blacklist = []

    if 'whitelist_file' in exceptions and exists(exceptions['whitelist_file']):
        f = open(exceptions['whitelist_file'], 'r')
        whitelist = filter(lambda l: l != '', map(lambda line: line.strip(), f.readlines()))
        f.close()
    
    if 'blacklist_file' in exceptions and exists(exceptions['blacklist_file']):
        f = open(exceptions['blacklist_file'], 'r')
        blacklist = filter(lambda l: l != '', map(lambda line: line.strip(), f.readlines()))
        f.close()
    
    return {'whitelist': whitelist, 'blacklist': blacklist}
    
def warn(to_be_warned, limits, exceptions, account, outgoing):
    if not to_be_warned:
        logging.debug('Nobody to be warned')
        return
    
    lists = parse_exceptions(exceptions)
    
    if 'report_address' in limits:
        f = open(limits['report_file'], "r")
        report_template = Template(f.read())
        report_email = limits['report_address']
    else:
        report_template = None
        
    for t in to_be_warned:
        f = open(limits['warning_file'], "r")
        text = Template(f.read())
        warning = text.substitute(to=t, email=t, limit=limits['count'])
        if report_template is not None:
            report = report_template.substitute(to=report_email, email=t, limit=limits['count'])
            logging.info('Sending report about user {email}'.format(email=t))
            send_email(report_email, "Report", report, outgoing)
        logging.info('Sending warning to user {email}'.format(email=t))
        send_email(t, "Warning", warning, outgoing, lists)

    already_warned = pickle.load(open(limits['warned_file'], "rb"))
    already_warned.extend(to_be_warned)
    pickle.dump(already_warned, open(limits['warned_file'], "wb" ))

    return

def main():
    if (len(sys.argv) > 1):
        conf_file = sys.argv[1]
    else:
        print "Usage: python limit.py CONF_FILE"
        exit()

    logging.basicConfig(
        format='[%(asctime)s] %(levelname)s:%(message)s',
        filename='limit.log',
        level=logging.INFO)

    logging.debug('Started list-limit.')
    
    account, outgoing, limits, exceptions = parse_conf(conf_file)

    offenders = get_offenders(account, limits)
    logging.debug("Offenders: {0}.".format(offenders))


    cleanup_already_warned(offenders, limits['warned_file'])

    to_be_warned = remove_already_warned(offenders, limits['warned_file'])

    logging.info("Unwarned offenders: {0}".format(to_be_warned))

    warn(to_be_warned, limits, exceptions, account, outgoing)
    logging.debug('Ending list-limit.')
    
if __name__ == "__main__":
    main()
