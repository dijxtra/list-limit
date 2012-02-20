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
import imaplib, collections, ConfigParser, pickle
from datetime import time, timedelta, datetime
from time import mktime
from email.parser import HeaderParser
from email.utils import parseaddr, parsedate
from os.path import exists
from string import Template

def mock_get_author_freqs(account, start):
    return {'nskoric@gmail.com' : 3, 'burek@pita.net' : 4, 'john@microsoft.com' : 1, 'mike@microsoft.com' : 5}

def get_author_freqs(account, start):
    """Connect to IMAP mail server, retreive mails and create dictionary of author frequencies.

    Arguments:
    server, port, username, password -- obvious
    list -- address of mailing list in question as it would appear in RFC2822 To: filed
    start -- start of current cycle: we count emails sent after this moment in time
    """
    M = imaplib.IMAP4_SSL(account['server'], account['port'])
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
        try:
            l = account['list']
        except KeyError:
            l = to
        if (account['list'] == to) and in_this_cycle(date, start):
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
    
    freqs = mock_get_author_freqs(account, start_time)
#    freqs = get_author_freqs(account, start_time)

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
        print "Already warned:", already_warned

    for w in already_warned:
        offenders.remove(w.strip())

    return offenders

def warn(to_be_warned, limits):
    print
    for t in to_be_warned:
        f = open(limits['warning_file'], "r")
        text = Template(f.read())
        finished = text.substitute(email=t, limit=limits['count'])
        print finished

    already_warned = pickle.load(open(limits['warned_file'], "rb"))
    already_warned.extend(to_be_warned)
    pickle.dump(already_warned, open(limits['warned_file'], "wb" ))

    return

def main():
    conf_file = "limit.conf"

    Config = ConfigParser.ConfigParser()
    Config.read(conf_file)
    account = dict(Config.items('Account'))
    limits = dict(Config.items('Limits'))

    try:
        list = Config.get('Account', 'list')
    except ConfigParser.NoOptionError:
        list =''
    try:
        limits['warned_file'] = Config.get('Limits', 'warned_file')
    except ConfigParser.NoOptionError:
        limits['warned_file'] ='warned.p'

    offenders = get_offenders(account, limits)
    print "Offenders:"
    for o in offenders:
        print o

    cleanup_already_warned(offenders, limits['warned_file'])

    to_be_warned = remove_already_warned(offenders, limits['warned_file'])
    
    print
    print "Unwarned offenders:"
    for t in to_be_warned:
        print t

    warn(to_be_warned, limits)
    
if __name__ == "__main__":
    main()
