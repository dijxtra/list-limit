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
import imaplib, collections, ConfigParser
from datetime import time, timedelta, datetime
from time import mktime
from email.parser import HeaderParser
from email.utils import parseaddr, parsedate

def get_author_freqs(server, port, username, password, list, start):
    """Connect to IMAP mail server, retreive mails and create dictionary of author frequencies.

    Arguments:
    server, port, username, password -- obvious
    list -- address of mailing list in question as it would appear in RFC2822 To: filed
    start -- start of current cycle: we count emails sent after this moment in time
    """
    M = imaplib.IMAP4_SSL(server, port)
    M.login(username, password)
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
        if ((list == to) or (list == '')) and in_this_cycle(date, start):
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

def get_offenders(conf_file):
    """Return list of emails offending the "number of mails daily" limit on a given mailing list.

    Arguments:
    conf_file -- Configuration file containing all data needed to do the task"""
    Config = ConfigParser.ConfigParser()
    Config.read(conf_file)

    host = Config.get('Account', 'host')
    port = Config.getint('Account', 'port')
    username = Config.get('Account', 'username')
    password = Config.get('Account', 'password')
    try:
        list = Config.get('Account', 'list')
    except ConfigParser.NoOptionError:
        list =''

    start_hour = Config.getint('Limits', 'start_hour')
    limit = Config.getint('Limits', 'count')
    
    start_time = get_start_time(start_hour)
    
    freqs = get_author_freqs(host, port, username, password, list, start_time)

#    print_leaderboard(freqs)

    offenders = extract_offenders(freqs, limit)
    
    return offenders

def print_leaderboard(freqs):
    """Print to the STDOUT list of authors with their current mail-count"""
    print "Leaderboard:"
    for f in sorted(freqs, key=freqs.get, reverse=True):
        print f, freqs[f]

def main():
    offenders = get_offenders("limit.conf")
    print "Offenders:"
    for o in offenders:
        print o
    
if __name__ == "__main__":
    main()
