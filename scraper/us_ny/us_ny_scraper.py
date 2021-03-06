# Recidiviz - a platform for tracking granular recidivism metrics in real time
# Copyright (C) 2018 Recidiviz, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
# =============================================================================


"""
us-ny-scraper.py
Recidivism data crawler for the state of New York, in the US.

Department: 
New York State - Dept of Corrections and Community Supervision (DOCCS)
 
Search type: 
- NYS-DOCCS allows for search by last name only
- However, we use a custom name list for DOCCS instead of the standard
    'last_names' list - see Notes.

Region-specific notes: 
    - DOCCS shows 'rough matches' that seem to iterate through the whole inmate
        database - making it much easier to query than most prison systems. 
            - As a result, the us-ny names list is custom 'aaardvark', since this
            query should be enough to get all inmates in the entire system.
            - Also as a result, we have to catch an exception in results parsing
            to know when we ran out of names / it looped back to the search page.
    - DOCCS is based on incarceration events, not prisoners. As a result, each 
        record produced by the scraper is for one stay in prison for one prisoner.
            - We add the field 'group_id' to entries which DOCCS says are for the 
            same person to aid in deduping people later on.


General scraping procedure:
    1. A starting search page --> (search, see 2)
    2. A results list (4x/page) --> (parse, see 2a and 2b)
        (2a) A list of inmate results --> (follow, each entry leads to 3)
        (2b) The 'next page' of results for the query --> (follow it, see 2)
    3. EITHER
        (3a) A disambiguation page (which time in jail would you like to see 
            for this inmate?)
        (3b) A details page for the inmate, about a specific incarceration event
"""

from datetime import datetime, date
from env_vars import EnvironmentVariable
from google.appengine.ext import ndb
from google.appengine.ext.db import Timeout, TransactionFailedError, InternalError
from google.appengine.api import memcache
from google.appengine.api import taskqueue
from google.appengine.api import urlfetch
from lxml import html
from models.inmate_facility_snapshot import InmateFacilitySnapshot
from models.record import Offense, SentenceDuration
from us_ny_inmate import UsNyInmate
from us_ny_record import UsNyRecord
from us_ny_scrape_session import ScrapeSession, ScrapedRecord

import dateutil.parser as parser
import json
import logging
import requests
import requests_toolbelt.adapters.appengine
import string
import time
import random
import re


START_URL = "http://nysdoccslookup.doccs.ny.gov/"
BASE_RESULTS_URL = "http://nysdoccslookup.doccs.ny.gov"
RESUME_URL = "http://recidiviz-123.appspot.com/resume_scraper?region=us_ny"
QUEUE_NAME = 'us-ny'
REGION = 'us_ny'
FAIL_COUNTER = REGION + "_next_page_fail_counter"

# Use the App Engine Requests adapter to make sure that Requests plays
# nice with GAE
requests_toolbelt.adapters.appengine.monkeypatch()
PROXY_DOMAIN = 'zproxy.luminati.io:22225/'
HEADERS = {'User-Agent': ('For any issues, concerns, or rate constraints, '
                          'e-mail team@recidiviz.com.')}


# TODO(andrew) - Create class to surround this with, with requirements for 
# the functions that will be called from recidiviz and worker such as setup(),
# start_query(), stop_scraper(), and resume_scraper().
def setup():
    """
    setup()
    Required by Scraper class. Is run prior to any specific scraping tasks for
    the region, and is allowed to trigger a small number of third-party network
    requests synchronously (without queues) to allow for initial session info, 
    etc. to be configured prior to scraping.     

    Args:
        None

    Returns:
        N/A
    """

    # Remove any old scraping session data
    cleanup()

    # Create new session
    new_session = ScrapeSession()
    try:
        new_session.put()
    except (Timeout, TransactionFailedError, InternalError):
        logging.warning("Couldn't create new session entity.")

    # Note: Since DOCCS creates a new form for every link to follow, it doesn't
    # look like we need to worry about session vars for the us-ny scraper.
    # get_session_vars()

    return


def start_query(first_name, last_name):
    """
    start_query()
    Required by Scraper class. Is run to kick off scraping for a particular 
    query (i.e., a particular name search). 

    Args:
        first_name: string, first name for inmate query (empty string if 
            last-name only search)
        last_name: string, last name for inmate query (required)

    Returns:
        N/A

        Enqueues task for initial search page scrape to get form/session params
        for the initial search request.
    """
    logging.info("Scraper starting up for name: %s %s" %
                 (first_name, last_name))

    # Search for the provided name
    params = {'first_name': first_name, 'last_name': last_name}

    serial_params = json.dumps(params)

    # Enqueue task to get new session vars
    taskqueue.add(url='/scraper',
                  queue_name=QUEUE_NAME,
                  params={'region': REGION,
                          'task': "scrape_search_page",
                          'params': serial_params})

    return


# SESSION MANAGEMENT #

# NOTE: US_NY DOESN'T NEED WEB SESSION MGT, SO COMMENTING RELEVANT SECTIONS OF
#       THIS SECTION OUT FOR THIS SCRAPER

"""
def get_session():
    ### Replace me with three double-quotes if uncommented
    get_session()
    Checks for session vars in memcache - if found, returns them. If not, 
    enqueues task to get new ones and store them in memcache. 

    Args:
        None

    Returns:
        Session info if successful, -1 if fails.

        Enqueues task to refresh cache if doesn't find current info in 
        memcache
    ### Replace me with three double-quotes if uncommented


    # Pull the memcache session info
    id = memcache.get('us_ny_session_var1')
    token = memcache.get('us_ny_session_var2')

    if (id is None) or (token is None):

        logging.info(REGION + " // Session cache miss, refreshing")


        # If any are missing, refresh the session info
        queue_session_refresh()

        # Fail the task, it'll get requeued with a delay (allowing time for the
        # session refresh task to finish)
        return -1

    else:
        results = {'token': token, 'id': id}
        return results

def queue_session_refresh():
    ### Replace me with three double-quotes if uncommented
    session_refresh()
    Forces refresh of session info, even if memcache still has prior
    values. 

    Args:
        None

    Returns:
        None

        Enqueues task to scrape search page for new session info
    ### Replace me with three double-quotes if uncommented

    # Session refreshes get their own (cross-region) queue, so they don't
    # get stuck behind tasks which are blocked on needing new session info.
    queue_name = "session-refresh"

    # Enqueue task to get new session vars
    task = taskqueue.add(
        url='/scraper',
        queue_name=queue_name,
        params={'region': REGION,
                'task': "get_session_vars"})

    return 

def get_session_vars():
    ### Replace me with three double-quotes if uncommented
    get_session_vars()
    Scrapes main search page to retrieve hidden form info for session

    Args:
        None

    Returns:
        None

        Stores new session info in memcache with TTL=1hr for fast access
    ### Replace me with three double-quotes if uncommented

    # Load the Search page on DOCCS, which will generate some tokens in the form
    search_page = requests.get(START_URL, timeout=REQUEST_TIMEOUT)
    search_tree = html.fromstring(search_page.content)

    # Extract said tokens and construct the URL for searches
    session_token = search_tree.cssselect("[name=K01]")[0].get("value")
    session_id = search_tree.cssselect("[name=DFH_STATE_TOKEN]")[0].get("value")

    # Store this info in memcache so tasks can easily get to it, with expiration
    # of an hour. This may be tweaked on a per-scraper basis, and this function
    # can be called at any time to refresh the info if stale.

    id_key = REGION + "_session_id"
    token_key = REGION + "_session_id"

    memcache.set(key=id_key, value=session_id, time=3600)
    memcache.set(key=token_key, value=session_token, time=3600)

    return
"""


def cleanup(end_session=True):
    """
    cleanup()
    Resets relevant session info after a scraping session is concluded and
    before another one starts.

    Args:
        end_session: Whether to also close out the current scraping session

    Returns:
        N/A
    """
    # Re-set the counter for when the server loses state
    memcache.set(key=FAIL_COUNTER, value=None)

    if end_session:
        # Close the last open scraping session by setting end date/time.
        open_sessions = get_open_sessions()
        for session in open_sessions:
            session.end = datetime.now()
            try:
                session.put()
            except (Timeout, TransactionFailedError, InternalError):
                logging.warning("Couldn't set end time on prior sessions.")

    # Purge any existing tasks
    queue = taskqueue.Queue(QUEUE_NAME)
    queue.purge()

    return


def stop_scrape():
    """
    stop_scrape()
    Required by Scraper class. Stops the scraper, even if in the middle of
    a session. In us_ny case, this is called by a cron job each day at 9am
    to ensure we don't interfere with regular users of the DOCCS site. The 
    while-loop is to ensure that even tasks in the process of running get
    shut down, since tasks spawn more tasks and keep the scraping going in 
    this system.

    Args:
        None

    Returns:
        N/A 
    """
    counter = 0
    while counter < 5:
        cleanup()
        time.sleep(5)
        counter += 1


def resume_scrape():
    """
    resume_scrape()
    Required by Scraper class. Starts the scraper up again at the same
    place (or roughly so) if it had to be stopped previously. This allows
    for cron jobs to start/stop scrapers at different times of day.

    Args:
        None

    Returns:
        N/A 
    """
    setup()

    logging.info("Sleeping for 40sec to allow taskqueue to purge...")

    # Give some time for the taskqueue to be cleared before creating new
    # tasks (gets purged in setup() above).
    time.sleep(40)

    logging.info("... sleep complete. Kicking off new scrape session.")

    # Get the most recent session (doesn't matter whether it was properly 
    # closed), and get the last name that was scraped in it.
    recent_sessions = get_open_sessions(open_only=False)

    for session in recent_sessions:
        if session.last_scraped:
            last_scraped = session.last_scraped
            break

    name_components = last_scraped.split(', ')
    params = {'first_name': name_components[1],
              'last_name': name_components[0]}
    serial_params = json.dumps(params)

    taskqueue.add(url='/scraper',
                  queue_name=QUEUE_NAME,
                  params={'region': REGION,
                          'task': "scrape_search_page",
                          'params': serial_params})


# SEARCH AND SEARCH RESULTS PAGES #

def scrape_search_page(params):
    """
    scrape_search_page()
    Gets the main search page, pulls form details, and queues request for
    inmate listings given our query. 

    Args:
        params: Dict of parameters
            first_name: string, first name for inmate query (empty string if 
            last-name only search)
            last_name: string, last name for inmate query (required)

    Returns:
        Nothing if successful, -1 if fails.

        Enqueues task with params from search page form, to fetch the first
        page of results.
    """

    params = json.loads(params)

    logging.info("Starting search for name in list: %s %s" %
                 (params['first_name'], params['last_name']))

    try:
        # Load the Search page on DOCCS, which will generate some tokens in the 
        # <form>
        proxies = get_proxies()
        search_page = requests.get(START_URL, proxies=proxies, headers=HEADERS)
    except requests.exceptions.RequestException as ce:
        log_error = "Error: {0}".format(ce)

        if ce.request:
            log_error += ("\n\nRequest headers: \n{0}"
                          "\n\nMethod: {1}"
                          "\n\nBody: \n{2} ")
            log_error = log_error.format(
                ce.request.headers,
                ce.request.method,
                ce.request.body)

        if ce.response:
            log_error += ("\n\nResponse: \n{0} / {1}"
                          "\n\nHeaders: \n{2}"
                          "\n\nText: \n{3}")
            log_error = log_error.format(
                ce.response.status_code,
                ce.response.reason,
                ce.response.headers,
                ce.response.text)

        logging.warning("Problem retrieving search page, failing task to "
                        "retry. \n\n%s" % log_error)
        return -1

    search_tree = html.fromstring(search_page.content)

    try:
        # Extract said tokens and construct the URL for searches
        session_K01 = search_tree.cssselect('[name=K01]')[0].get("value")
        session_token = search_tree.cssselect('[name=DFH_STATE_TOKEN]')[0].get("value")
        session_action = search_tree.xpath('//div[@id="content"]/form/@action')[0]
    except IndexError:
        logging.error("Search page not understood. HTML:\n\n%s" %
                      search_page.content)
        return -1

    search_results_params = {
        'first_page': True,
        'k01': session_K01,
        'token': session_token,
        'action': session_action,
        'first_name': params['first_name'],
        'last_name': params['last_name']}

    # Serialize params so they can make it through a POST request
    search_results_params_serial = json.dumps(search_results_params)

    # Enqueue task to get results and parse them
    taskqueue.add(url='/scraper',
                  queue_name=QUEUE_NAME,
                  params={'region': REGION,
                          'task': "scrape_search_results_page",
                          'params': search_results_params_serial})

    return


def scrape_search_results_page(params):
    """
    get scrape_search_page()
    Fetches search results page, parses results to extract inmate listings
    and params for the next page of results. Enqueues tasks to scrape both
    the individual listings and next page of results.

    Args:
        params: Dict of parameters. This is how DOCCS keeps track of where you
        are and what you're requesting. Not all of the parameters are
        understood, and some are frequently empty values.
            first_name: string, first name for inmate query (empty string if 
            last-name only search)
            last_name: string, last name for inmate query (required)
            k01: a request parameter for results, scraped from the form
            token: DFH_STATE_TOKEN - session info from the scraped form
            action: the 'action' attr from the scraped form - URL to POST to
            ---params below only apply for the first page of search results---
            first_page: True / exists only if this is requesting the first page
                of results
            ---params below only apply for 'next page' results---
            clicki: a request parameter for results, scraped from the form
            dini: a request parameter for results, scraped from the form
            k01,k02,k03,k04,k05,k06: request parameters for results, scraped
                from the form
            map_token: a request parameter for results, scraped from the form
            next: a request parameter for results, scraped from the form

    Returns:
        Nothing if successful, -1 if fails.

        Enqueues task with params from search page form, to fetch the first
        page of results.
    """

    params = json.loads(params)

    url = BASE_RESULTS_URL + str(params['action'])

    try:

        proxies = get_proxies()

        # The request for the first results page is a little unique 
        if 'first_page' in params:

            # Create a request using the provided params
            results_page = requests.post(url, proxies=proxies, headers=HEADERS,
                                         data={
                                             'K01': params['k01'],
                                             'DFH_STATE_TOKEN': params['token'],
                                             'DFH_MAP_STATE_TOKEN': '',
                                             'M00_LAST_NAMEI': params['last_name'],
                                             'M00_FIRST_NAMEI': params['first_name'],
                                             'M00_MID_NAMEI': '',
                                             'M00_NAME_SUFXI': '',
                                             'M00_DOBCCYYI': '',
                                             'M00_DIN_FLD1I': '',
                                             'M00_DIN_FLD2I': '',
                                             'M00_DIN_FLD3I': '',
                                             'M00_NYSID_FLD1I': '',
                                             'M00_NYSID_FLD2I': ''
                                         })

        else:

            # Create a request using the provided params
            results_page = requests.post(url, proxies=proxies, headers=HEADERS,
                                         data={
                                             'M13_PAGE_CLICKI': params['clicki'],
                                             'M13_SEL_DINI': params['dini'],
                                             'K01': params['k01'],
                                             'K02': params['k02'],
                                             'K03': params['k03'],
                                             'K04': params['k04'],
                                             'K05': params['k05'],
                                             'K06': params['k06'],
                                             'DFH_STATE_TOKEN': params['token'],
                                             'DFH_MAP_STATE_TOKEN': params['map_token'],
                                             'next': params['next'],
                                         })

    except requests.exceptions.RequestException as ce:
        printable = ("Error: %s" % ce)
        if ce.request:
            printable += "\n\nRequest headers:\n%s" % str(ce.request.headers)
            printable += "\n\nMethod: %s" % ce.request.method
            printable += "\n\nBody: \n%s" % ce.request.body
        if ce.response:
            printable += ("\n\nResponse: \n%s / %s" %
                          (ce.response.status_code, ce.response.reason))
            printable += "\n\nHeaders: \n%s" % str(ce.response.headers)
            printable += "\n\nText: \n%s" % ce.response.text
        logging.warning("Problem retrieving search results page, "
                        "failing task to retry. \n\n%s" % printable)
        return -1

    results_tree = html.fromstring(results_page.content)

    # Parse the rows in the search results list
    result_list = results_tree.xpath('//table[@id="dinlist"]/tr/td/form')

    for row in result_list:
        result_params = {}

        # Parse result rows, pull form info to follow link
        result_params['action'] = row.xpath('attribute::action')[0]
        result_params['clicki'] = row.xpath(
            './div/input[@name="M13_PAGE_CLICKI"]/@value')[0]
        result_params['dini'] = row.xpath(
            './div/input[@name="M13_SEL_DINI"]/@value')[0]
        result_params['k01'] = row.xpath(
            './div/input[@name="K01"]/@value')[0]
        result_params['k02'] = row.xpath(
            './div/input[@name="K02"]/@value')[0]
        result_params['k03'] = row.xpath(
            './div/input[@name="K03"]/@value')[0]
        result_params['k04'] = row.xpath(
            './div/input[@name="K04"]/@value')[0]
        result_params['k05'] = row.xpath(
            './div/input[@name="K05"]/@value')[0]
        result_params['k06'] = row.xpath(
            './div/input[@name="K06"]/@value')[0]
        result_params['token'] = row.xpath(
            './div/input[@name="DFH_STATE_TOKEN"]/@value')[0]
        result_params['map_token'] = row.xpath(
            './div/input[@name="DFH_MAP_STATE_TOKEN"]/@value')[0]
        result_params['dinx_name'] = row.xpath(
            './div/input[@type="submit"]/@name')[0]
        result_params['dinx_val'] = row.xpath(
            './div/input[@type="submit"]/@value')[0]

        # Enqueue tasks to follow that link / get result
        result_params['first_name'] = params['first_name']
        result_params['last_name'] = params['last_name']
        result_params = json.dumps(result_params)

        taskqueue.add(url='/scraper',
                      queue_name=QUEUE_NAME,
                      params={'region': REGION,
                              'task': "scrape_inmate",
                              'params': result_params})

    # Parse the 'next' button's embedded form
    next_params = {}

    try:
        next_button = results_tree.xpath('//div[@id="content"]/form')[0]

        next_params['action'] = next_button.xpath('attribute::action')[0]
        next_params['clicki'] = next_button.xpath(
            './div/input[@name="M13_PAGE_CLICKI"]/@value')[0]
        next_params['dini'] = next_button.xpath(
            './div/input[@name="M13_SEL_DINI"]/@value')[0]
        next_params['k01'] = next_button.xpath(
            './div/input[@name="K01"]/@value')[0]
        next_params['k02'] = next_button.xpath(
            './div/input[@name="K02"]/@value')[0]
        next_params['k03'] = next_button.xpath(
            './div/input[@name="K03"]/@value')[0]
        next_params['k04'] = next_button.xpath(
            './div/input[@name="K04"]/@value')[0]
        next_params['k05'] = next_button.xpath(
            './div/input[@name="K05"]/@value')[0]
        next_params['k06'] = next_button.xpath(
            './div/input[@name="K06"]/@value')[0]
        next_params['token'] = next_button.xpath(
            './div/input[@name="DFH_STATE_TOKEN"]/@value')[0]
        next_params['map_token'] = next_button.xpath(
            './div/input[@name="DFH_MAP_STATE_TOKEN"]/@value')[0]
        next_params['next'] = next_button.xpath(
            './div/div/input[@name="next"]/@value')[0]

        # Update session to remember the first person on this results page, to
        # ensure we can pick up where we left off later if desired. Note that
        # us_ny scraper can only crawl 1x search results page at a time, so 
        # there is no risk of contention.
        last_scraped = results_tree.xpath(
            '//td[@headers="name"]')[0].text_content().strip()
        update_session_result = update_last_scraped(last_scraped)

        if not update_session_result:
            # Failed to persist the name into the current session entity
            return -1

    except IndexError:
        # We got a page we didn't expect - results_parsing_failure will
        # attempt to disambiguate why.
        wind_down = results_parsing_failure()

        if wind_down:
            # End task peacefully
            return
        else:
            # Fail task to retry
            return -1

    # Enqueue task to follow that link / get result
    next_params['first_name'] = params['first_name']
    next_params['last_name'] = params['last_name']
    next_params = json.dumps(next_params)

    taskqueue.add(url='/scraper',
                  queue_name=QUEUE_NAME,
                  params={'region': REGION,
                          'task': "scrape_search_results_page",
                          'params': next_params})

    return


# INMATE PAGES #

def scrape_inmate(params):
    """
    scrape_inmate()
    Fetches inmate listing page. This sometimes turns out to be a
    disambiguation page, as there may be multiple incarceration records in
    DOCCS for the person you've selected. If so, shunts details over to
    scrape_disambiguation(). If actual results page, pulls details from page
    and sends to store_record.

    Args:
        params: Dict of parameters. This is how DOCCS keeps track of where you
        are and what you're requesting. Not all of the parameters are
        understood, and some are frequently empty values.
            first_name: string, first name for inmate query (empty string if 
            last-name only search)
            last_name: string, last name for inmate query (required)
            token: DFH_STATE_TOKEN - session info from the scraped form
            action: the 'action' attr from the scraped form - URL to POST to
            dini: a request parameter for results, scraped from the form
            k01,k02,k03,k04,k05,k06: request parameters for results, scraped
                from the form
            map_token: a request parameter for results, scraped from the form
            dinx_name: form results are d1-d4, this is the name attr which we 
                store as a key in the params (result: {dinx_name: dinx_val})
            dinx_val: value for the dinx_name parameter
            ---params below only apply if we did NOT arrive from a 
                disambiguation page / this inmate only has one listing---
            clicki: a request parameter for results, scraped from the form

    Returns:
        Nothing if successful, -1 if fails.

        Enqueues task with params from search page form, to fetch the first
        page of results.
    """

    params = json.loads(params)

    inmate_details = {}
    url = BASE_RESULTS_URL + str(params['action'])

    try:

        proxies = get_proxies()

        # Create a request using the provided params. How we structure this varies
        # a bit depending on whether we got here from a results page or a 
        # disambiguation page.
        if 'group_id' in params:
            inmate_details['group_id'] = params['group_id']
            inmate_details['linked_records'] = params['linked_records']

            # Create a request using the provided params
            inmate_page = requests.post(url, proxies=proxies, headers=HEADERS,
                                        data={
                                            'M12_SEL_DINI': params['dini'],
                                            'K01': params['k01'],
                                            'K02': params['k02'],
                                            'K03': params['k03'],
                                            'K04': params['k04'],
                                            'K05': params['k05'],
                                            'K06': params['k06'],
                                            'DFH_STATE_TOKEN': params['token'],
                                            'DFH_MAP_STATE_TOKEN': params['map_token'],
                                            params['dinx_name']: params['dinx_val'],
                                        })

        else:
            # Create a request using the provided params
            inmate_page = requests.post(url, proxies=proxies, headers=HEADERS,
                                        data={
                                            'M13_PAGE_CLICKI': params['clicki'],
                                            'M13_SEL_DINI': params['dini'],
                                            'K01': params['k01'],
                                            'K02': params['k02'],
                                            'K03': params['k03'],
                                            'K04': params['k04'],
                                            'K05': params['k05'],
                                            'K06': params['k06'],
                                            'DFH_STATE_TOKEN': params['token'],
                                            'DFH_MAP_STATE_TOKEN': params['map_token'],
                                            params['dinx_name']: params['dinx_val'],
                                        })

    except requests.exceptions.RequestException as ce:
        printable = ("Error: %s" % ce)
        if ce.request:
            printable += "\n\nRequest headers:\n%s" % str(ce.request.headers)
            printable += "\n\nMethod: %s" % ce.request.method
            printable += "\n\nBody: \n%s" % ce.request.body
        if ce.response:
            printable += ("\n\nResponse: \n%s / %s" %
                          (ce.response.status_code, ce.response.reason))
            printable += "\n\nHeaders: \n%s" % str(ce.response.headers)
            printable += "\n\nText: \n%s" % ce.response.text

        logging.warning("Problem retrieving inmate details, failing task to "
                        "retry. \n\n%s" % printable)
        return -1

    page_tree = html.fromstring(inmate_page.content)

    # First, test if we got a disambiguation page (inmate has had more than 
    # one stay in prison system, page wants to know which you want to see)
    details_page = page_tree.xpath('//div[@id="ii"]')

    if details_page:

        # Create xpath selectors for the parts of the page we want to scrape
        id_and_locale_rows = details_page[0].xpath("./table[contains(@summary, 'Identifying')]/tr")
        crimes_rows = details_page[0].xpath("./table[contains(@summary, 'crimes')]/tr")
        sentence_rows = details_page[0].xpath("./table[contains(@summary, 'sentence')]/tr")

        # Make sure the tables on the page are what we're expecting
        expected_first_row_id = "DIN (Department Identification Number)"
        expected_first_row_crimes = "Crime"
        expected_first_row_sentences = "Aggregate Minimum Sentence"

        actual_first_row_id = (
            id_and_locale_rows[0].xpath("./td")[0].text_content().strip())
        actual_first_row_crimes = (
            crimes_rows[0].xpath("./th")[0].text_content().strip())
        actual_first_row_sentences = (
            sentence_rows[0].xpath("./td")[0].text_content().strip())

        if (actual_first_row_id != expected_first_row_id or
                actual_first_row_crimes != expected_first_row_crimes or
                actual_first_row_sentences != expected_first_row_sentences):

            # This isn't the page we were expecting
            logging.warning("Did not find expected tables on inmates page. "
                            "Page received: \n" +
                            html.tostring(page_tree, pretty_print=True))
            return -1

        else:
            crimes = []

            # Capture table data from each details table on the page
            for row in id_and_locale_rows:
                row_data = row.xpath('./td')
                key, value = normalize_key_value_row(row_data)
                inmate_details[key] = value

            for row in crimes_rows:
                row_data = row.xpath('./td')

                # One row is the table headers / has no <td> elements
                if not row_data:
                    pass
                else:
                    crime_description, crime_class = normalize_key_value_row(row_data)
                    crime = {'crime': crime_description,
                             'class': crime_class}

                    # Only add to the list if row is non-empty
                    if crime['crime']:
                        crimes.append(crime)

            for row in sentence_rows:
                row_data = row.xpath('./td')
                key, value = normalize_key_value_row(row_data)
                inmate_details[key] = value

            inmate_details['crimes'] = crimes

        logging_name = "%s %s" % (params['first_name'], params['last_name'])
        logging_name = logging_name.strip()
        logging.info("(%s) Scraped inmate: %s" %
                     (logging_name, inmate_details['Inmate Name']))

        return store_record(inmate_details)

    else:
        # We're on a disambiguation page, not an actual details page. Scrape 
        # the disambig page and follow each link.

        # We can call this one without creating a task, it doesn't create a new
        # network call
        return scrape_disambiguation(page_tree,
                                     params['first_name'],
                                     params['last_name'])


def scrape_disambiguation(page_tree, first_name, last_name):
    """
    scrape_disambiguation()
    In attempting to fetch an inmate, the scrape_inmate received a 
    disambig page - asking which incarceration event for that inmate they
    wanted. This function takes that result page, parses it, and enqueues a
    new task to scrape each entry from the disambig page.

    Args:
        page_tree: lxml.html parsed version of the disambig page
        first_name: string, first name for inmate query (empty string if 
            last-name only search)
        last_name: string, last name for inmate query (required)

    Returns:
        Nothing if successful, -1 if fails.

        Enqueues task for each incarceration event listed on the page.
    """
    # Create an ID to group these entries with - DOCCS doesn't tell us how it 
    # groups these / give us a persistent ID for inmates, but we want to know
    # each of the entries scraped from this page were about the same person.
    group_id = generate_id(UsNyInmate)
    new_tasks = []
    department_identification_numbers = []

    # Parse the results list
    result_list = page_tree.xpath('//div[@id="content"]/table/tr/td/form')

    if not result_list:
        logging.warning("Malformed inmate or disambig page, failing task to "
                        "re-queue.")
        return -1

    for row in result_list:
        result_params = {}

        result_params['group_id'] = group_id

        # Parse result row and relevant form info to follow link
        result_params['action'] = row.xpath('attribute::action')[0]
        result_params['dini'] = row.xpath(
            './div/input[@name="M12_SEL_DINI"]/@value')[0]
        result_params['k01'] = row.xpath(
            './div/input[@name="K01"]/@value')[0]
        result_params['k02'] = row.xpath(
            './div/input[@name="K02"]/@value')[0]
        result_params['k03'] = row.xpath(
            './div/input[@name="K03"]/@value')[0]
        result_params['k04'] = row.xpath(
            './div/input[@name="K04"]/@value')[0]
        result_params['k05'] = row.xpath(
            './div/input[@name="K05"]/@value')[0]
        result_params['k06'] = row.xpath(
            './div/input[@name="K06"]/@value')[0]
        result_params['token'] = row.xpath(
            './div/input[@name="DFH_STATE_TOKEN"]/@value')[0]
        result_params['map_token'] = row.xpath(
            './div/input[@name="DFH_MAP_STATE_TOKEN"]/@value')[0]
        result_params['dinx_name'] = row.xpath(
            './div/input[@type="submit"]/@name')[0]
        result_params['dinx_val'] = row.xpath(
            './div/input[@type="submit"]/@value')[0]

        department_identification_numbers.append(result_params['dinx_val'])
        new_tasks.append(result_params)

    for task_params in new_tasks:

        """ 
        The disambig page produces far more rows than are visible, each with
        a form element you can click - programmatically, these look nearly
        identical to actual result rows. 

        The only differences are 
          a) they have empty 'value' attr in the 'submit' element / (thus are
          empty / invisible in the UI), and 
          b) they go back to the search results instead of listing another 
          record. 

        To avoid the latter mucking up our parsing, we test dinx_val to skip 
        these entries.
        """
        if task_params['dinx_val']:

            dept_id_number = task_params['dinx_val']

            # Double-check that we haven't already processed this entry while
            # scraping another disambig page for this same inmate

            current_session = get_open_sessions(most_recent_only=True)

            if current_session is None:
                # The session's been closed, we should peacefully end scraping
                logging.info("No open sessions, exiting without creating new "
                             "tasks for disambig page results.")
                return

            scraped_record = ScrapedRecord.query(ndb.AND(
                ScrapedRecord.record_id == dept_id_number,
                ScrapedRecord.created_on > current_session.start)).get()

            if scraped_record:
                # Skip this inmate, move to next task to enqueue
                logging.info("We already scraped record %s, skipping." %
                             dept_id_number)
                continue

            # Otherwise, let's schedule scraping it and add it to the list
            new_scraped_record = ScrapedRecord(record_id=dept_id_number)
            try:
                new_scraped_record.put()
            except (Timeout, TransactionFailedError, InternalError):
                logging.warning("Couldn't persist ScrapedRecord entry, "
                                "record_id: %s" % dept_id_number)

            # Enqueue task to follow that link / scrape record
            task_params['first_name'] = first_name
            task_params['last_name'] = last_name
            task_params['linked_records'] = department_identification_numbers
            task_params = json.dumps(task_params)

            taskqueue.add(url='/scraper',
                          queue_name=QUEUE_NAME,
                          params={'region': REGION,
                                  'task': "scrape_inmate",
                                  'params': task_params})

    return


def store_record(inmate_details):
    """
    store_record()
    We've scraped an incarceration details page, and want to store the data we
    found. This function does some post-processing on the scraped data, and
    feeds it into the datastore in a way that can be indexed / queried in the
    future.

    Args:
        inmate_details: the results of the scrape, stored in a dict object.

    Returns:
        Nothing if successful, -1 if fails.
    """

    # INMATE LISTING

    department_identification_numbers = []
    if 'linked_records' in inmate_details:
        department_identification_numbers.extend(
            inmate_details['linked_records'])
    else:
        department_identification_numbers.append(
            inmate_details['DIN (Department Identification Number)'])

    old_id = link_inmate(department_identification_numbers)

    if old_id:
        # Found old entry for this inmate
        inmate_id = old_id
    else:
        # Failed to find old entry, create new inmate_id
        if 'group_id' in inmate_details:
            # If we find no prior records, use the group_id generated earlier in 
            # this scraping session as the inmate_id, so as to tie this record 
            # to the linked ones for the same inmate.
            inmate_id = inmate_details['group_id']
        else:
            inmate_id = generate_id(UsNyInmate)

    inmate = UsNyInmate.get_or_insert(inmate_id)

    # Some pre-work to massage values out of the data
    inmate_name = inmate_details['Inmate Name'].split(', ')
    inmate_dob = inmate_details['Date of Birth']
    inmate_age = None
    if inmate_dob:
        # We received a string for the birth date
        inmate_dob = parse_date_string(inmate_dob, inmate_id)
        if inmate_dob:
            # The string was successfully converted to datetime
            inmate_age = calculate_age(inmate_dob)
    inmate_sex = inmate_details['Sex'].lower()
    inmate_race = inmate_details['Race / Ethnicity'].lower()

    # NY-specific fields
    inmate.us_ny_inmate_id = inmate_id

    # General Inmate fields
    if inmate_dob:
        inmate.birthday = inmate_dob
    if inmate_age:
        inmate.age = inmate_age
    if inmate_sex:
        inmate.sex = inmate_sex
    if inmate_race:
        inmate.race = inmate_race
    inmate.inmate_id = inmate_id
    inmate.inmate_id_is_fuzzy = True
    inmate.last_name = inmate_name[0]
    if len(inmate_name) > 1:
        inmate.given_names = inmate_name[1]
    inmate.region = REGION

    try:
        inmate_key = inmate.put()
    except (Timeout, TransactionFailedError, InternalError):
        # Datastore error - fail task to trigger queue retry + backoff
        logging.warning("Couldn't persist inmate: %s" % inmate_id)
        return -1

    # CRIMINAL RECORD ENTRY

    record_id = inmate_details['DIN (Department Identification Number)']

    record = UsNyRecord.get_or_insert(record_id, parent=inmate_key)

    # Some pre-work to massage values out of the data
    last_custody = inmate_details['Date Received (Current)']
    if last_custody:
        last_custody = parse_date_string(last_custody, inmate_id)
    first_custody = inmate_details['Date Received (Original)']
    if first_custody:
        first_custody = parse_date_string(first_custody, inmate_id)
    admission_type = inmate_details['Admission Type']
    county_of_commit = inmate_details['County of Commitment']
    custody_status = inmate_details['Custody Status']
    released = (custody_status != "IN CUSTODY")
    min_sentence = inmate_details['Aggregate Minimum Sentence']
    if min_sentence:
        min_sentence = parse_sentence_duration(min_sentence, inmate_id)
    max_sentence = inmate_details['Aggregate Maximum Sentence']
    if max_sentence:
        max_sentence = parse_sentence_duration(max_sentence, inmate_id)
    earliest_release_date = inmate_details['Earliest Release Date']
    if earliest_release_date:
        earliest_release_date = parse_date_string(earliest_release_date, inmate_id)
    earliest_release_type = inmate_details['Earliest Release Type']
    parole_hearing_date = inmate_details['Parole Hearing Date']
    if parole_hearing_date:
        parole_hearing_date = parse_date_string(parole_hearing_date, inmate_id)
    parole_hearing_type = inmate_details['Parole Hearing Type']
    parole_elig_date = inmate_details['Parole Eligibility Date']
    if parole_elig_date:
        parole_elig_date = parse_date_string(parole_elig_date, inmate_id)
    cond_release_date = inmate_details['Conditional Release Date']
    if cond_release_date:
        cond_release_date = parse_date_string(cond_release_date, inmate_id)
    max_expir_date = inmate_details['Maximum Expiration Date']
    if max_expir_date:
        max_expir_date = parse_date_string(max_expir_date, inmate_id)
    max_expir_date_parole = (
        inmate_details['Maximum Expiration Date for Parole Supervision'])
    if max_expir_date_parole:
        max_expir_date_parole = parse_date_string(max_expir_date_parole, inmate_id)
    max_expir_date_superv = (
        inmate_details['Post Release Supervision Maximum Expiration Date'])
    if max_expir_date_superv:
        max_expir_date_superv = parse_date_string(max_expir_date_superv, inmate_id)
    parole_discharge_date = inmate_details['Parole Board Discharge Date']
    if parole_discharge_date:
        parole_discharge_date = parse_date_string(parole_discharge_date, inmate_id)
    last_release = (
        inmate_details['Latest Release Date / Type (Released Inmates Only)'])
    if last_release:
        release_info = last_release.split(" ", 1)
        last_release_date = parse_date_string(release_info[0], inmate_id)
        last_release_type = release_info[1]

    record_offenses = []
    for crime in inmate_details['crimes']:
        crime = Offense(
            crime_description=crime['crime'],
            crime_class=crime['class'])
        record_offenses.append(crime)

    # NY-specific record fields
    if last_custody:
        record.last_custody_date = last_custody
    if admission_type:
        record.admission_type = admission_type
    if county_of_commit:
        record.county_of_commit = county_of_commit
    if custody_status:
        record.custody_status = custody_status
    if last_release:
        record.last_release_type = last_release_type
        record.last_release_date = last_release_date
    if min_sentence:
        min_sentence_duration = SentenceDuration(
            life_sentence=min_sentence['Life'],
            years=min_sentence['Years'],
            months=min_sentence['Months'],
            days=min_sentence['Days'])
    else:
        min_sentence_duration = None
    if max_sentence:
        max_sentence_duration = SentenceDuration(
            life_sentence=max_sentence['Life'],
            years=max_sentence['Years'],
            months=max_sentence['Months'],
            days=max_sentence['Days'])
    else:
        max_sentence_duration = None
    if earliest_release_date:
        record.earliest_release_date = earliest_release_date
    if earliest_release_type:
        record.earliest_release_type = earliest_release_type
    if parole_hearing_date:
        record.parole_hearing_date = parole_hearing_date
    if parole_hearing_type:
        record.parole_hearing_type = parole_hearing_type
    if parole_elig_date:
        record.parole_elig_date = parole_elig_date
    if cond_release_date:
        record.cond_release_date = cond_release_date
    if max_expir_date:
        record.max_expir_date = max_expir_date
    if max_expir_date_parole:
        record.max_expir_date_parole = max_expir_date_parole
    if max_expir_date_superv:
        record.max_expir_date_superv = max_expir_date_superv
    if parole_discharge_date:
        record.parole_discharge_date = parole_discharge_date

    # General Record fields
    if record_offenses:
        record.offense = record_offenses
    if first_custody:
        record.custody_date = first_custody
    if min_sentence_duration:
        record.min_sentence_length = min_sentence_duration
    if max_sentence_duration:
        record.max_sentence_length = max_sentence_duration
    if inmate_dob:
        record.birthday = inmate_dob
    if inmate_sex:
        record.sex = inmate_sex
    if inmate_race:
        record.race = inmate_race
    record.last_name = inmate_name[0]
    record.given_names = inmate_name[1]
    record.record_id = record_id
    record.is_released = released

    try:
        record_key = record.put()
    except (Timeout, TransactionFailedError, InternalError):
        logging.warning("Couldn't persist record: %s" % record_id)
        return -1

    # FACILITY SNAPSHOT

    # Check if the most recent facility snapshot had the facility we see
    last_facility_snapshot = InmateFacilitySnapshot.query(
        ancestor=record_key).order(-InmateFacilitySnapshot.snapshot_date).get()

    scraped_facility = inmate_details['Housing / Releasing Facility']

    if (not last_facility_snapshot) \
            or (last_facility_snapshot.facility != scraped_facility):

        # The facility doesn't match last snapshot, or there was no last
        # snapshot. Record a new one.
        facility_snapshot = InmateFacilitySnapshot(
            parent=record_key,
            facility=scraped_facility)

        try:
            facility_snapshot.put()
        except (Timeout, TransactionFailedError, InternalError):
            logging.warning("Couldn't persist facility snapshot for record: %s" %
                            record_id)
            return -1

    if 'group_id' in inmate_details:
        logging.info("Stored record for %s %s, inmate %s, in group %s, for "
                     "record %s." % (
                         inmate_name[1],
                         inmate_name[0],
                         inmate_id,
                         inmate_details['group_id'],
                         record_id))
    else:
        logging.info("Stored record for %s %s, inmate %s, (no group), for "
                     "record %s." % (
                         inmate_name[1],
                         inmate_name[0],
                         inmate_id,
                         record_id))

    return


def parse_sentence_duration(term_string, inmate_id):
    """
    parse_sentence_duration()
    For the 'Maximum Aggregate Sentence' and 'Minimum Aggregate Sentence'
    results, the scraped string often looks like one of these:
        "00 Years, 000 Months, 000 Days",
        "04 Years, 002 Months, 000 Days",
        "LIFE Years, 999 Months, 999 Days",
    etc. There is a bit of inconsistency on number of digits or exact string.
    This function takes the string, and turns it into a dictionary with
    year/month/day values and a 'Life Sentence' boolean.

    Args:
        term_string: (str) Scraped string similar to in the description above
        inmate_id: (str) Inmate ID this date is for, for logging if parse fails

    Returns:
        dict of values - 
            'Life' (bool) whether sentence is a life term,
            'Years' (int) # years
            'Months' (int) # months
            'Days' (int) # days


        Enqueues task for each incarceration event listed on the page.
    """
    if term_string.startswith("LIFE"):

        result = {'Life': True,
                  'Years': 0,
                  'Months': 0,
                  'Days': 0}

    else:
        parsed_nums = re.findall('\d+', term_string)

        if (not parsed_nums) or (len(parsed_nums) < 3):
            logging.info("Couldn't parse term string '%s' for inmate: %s" %
                         (term_string, inmate_id))
            result = None
        else:
            years = int(parsed_nums[0])
            months = int(parsed_nums[1])
            days = int(parsed_nums[2])

            result = {'Life': False,
                      'Years': years,
                      'Months': months,
                      'Days': days}

    return result


def parse_date_string(date_string, inmate_id):
    """
    parse_date_string()
    Dates are expressed differently in different records, typically following
    one of these patterns:
        "07/2001",
        "12/21/1991",
        "06/14/13",
    etc. This function parses several common variants and returns a datetime.

    Args:
        date_string: (str) Scraped string containing a date
        inmate_id: (str) Inmate ID this date is for, for logging if parse fails

    Returns:
        Python datetime object representing the date parsed from the string, or
        None if string wasn't one of our expected values (this is common, often
        NONE or LIFE are put in for these if life sentence).
    """
    try:
        result = parser.parse(date_string)
    except ValueError:
        logging.info("Couldn't parse date string '%s' for inmate: %s" %
                     (date_string, inmate_id))
        result = None

    return result


def link_inmate(record_list):
    """
    link_inmate()
    Matches DIN (record IDs) to previously scraped records, looks up associated 
    inmates, then returns that inmate_id so we can update the same person rather
    than duplicating the inmate.

    Args:
        record_list: (list of strings) List of DINs (record IDs) to check.

    Returns:
        The found inmate_id from prior instance, or None if none found.
    """

    for linked_record in record_list:
        query = UsNyRecord.query(UsNyRecord.record_id == linked_record)
        result = query.get()
        if result:
            # Set inmate_id to the inmate_id of the Inmate referenced by that record
            prior_inmate_key = result.key.parent()
            prior_inmate = prior_inmate_key.get()
            inmate_id = prior_inmate.inmate_id

            logging.info("Found an earlier record with an inmate ID " +
                         inmate_id + ", using that.")
            return inmate_id

    # Made it through the whole list without finding prior versions
    return None


def generate_id(entity_kind):
    """
    generate_id()
    Generates a new, unique identifier for the entity kind provided.

    Args:
        entity_kind: (ndb entity) Entity kind to check uniqueness of generated
            id.

    Returns:
        The new ID / key name.
    """

    # Generate new key
    new_id = ''.join(random.choice(string.ascii_uppercase +
                                   string.ascii_lowercase +
                                   string.digits) for _ in range(10))

    # Double-check it isn't a collision
    test_key = ndb.Key(entity_kind, new_id)
    key_result = test_key.get()

    if key_result is not None:
        # Collision, try again
        return generate_id(entity_kind)
    else:
        return new_id


def normalize_key_value_row(row_data):
    """
    normalize_key_value_row()
    Removes extraneous (leading, trailing, internal) whitespace from scraped
    data. 

    Args:
        row_data: (list) One row of data in a list (key/value pair)

    Returns:
        List of cleaned strings, in the same order as provided.
    """
    key = ' '.join(row_data[0].text_content().split())
    value = ' '.join(row_data[1].text_content().split())
    return key, value


def calculate_age(birth_date):
    """
    calculate_age()
    Determines age of inmate based on her or his birth date. Note: We don't
    know the timezone of birth, so we use local time for us. Result may be 
    off by up to a day.

    Args:
        birth_date: (datetime) Date of birth as reported by prison system

    Returns:
        (int) Age of inmate 
    """
    today = date.today()
    age = today.year - birth_date.year - ((today.month, today.day) <
                                          (birth_date.month, birth_date.day))

    return age


def get_open_sessions(open_only=True, most_recent_only=False):
    """
    get_open_sessions()
    Finds and returns the list of session that were started but not 
    closed, ordered by most recent. If most_recent_only, just returns
    the most recent match.

    Args:
        N/A

    Returns:
        Current ScrapeSession, or None if no open session found  
    """
    session_query = ScrapeSession.query()

    if open_only:
        # This must be an equality operator instead of `is None` for `filter` to work
        session_query = session_query.filter(ScrapeSession.end == None)

    session_query = session_query.order(-ScrapeSession.start)

    if most_recent_only:
        session_results = session_query.get()
    else:
        session_results = session_query.fetch()

    return session_results


def update_last_scraped(last_scraped):
    """
    update_last_scraped()
    Updates the most recent open session entity with the name seen at the
    top of the most recently scraped results page.

    Args:
        last_scraped: Name at the top of the most recent page of results

    Returns:
        True if successful
        False if not
    """
    current_session = get_open_sessions(most_recent_only=True)
    if current_session:
        current_session.last_scraped = last_scraped
        try:
            current_session.put()
        except (Timeout, TransactionFailedError, InternalError):
            logging.warning("Couldn't persist last scraped name: %s" %
                            last_scraped)
            return False
    else:
        logging.error("No open sessions found!")
        return False

    return True


def results_parsing_failure():
    """
    results_parsing_failure()
    We didn't get the page we expected while retrieving a search results
    page. We retry three times (keeping track in memcache), which is 
    long enough for most transient errors to go away.

    If we fail three times in a row (with backoff), we first check if we've
    completed the alphabet. On the last page, when we click 'Next 4 results',
    DOCCS just takes the user back to the main search page (which could be why
    trying to parse it like a result page failed). If we did, we just shut 
    down the scraper because this is success.

    If not, we assume DOCCS has lost state and no longer knows what we're
    asking for. In this case we clean up the current scraping session, purge
    all other tasks in the queue, and kick off a new scraping session to
    get new state in DOCCS to continue scraping using.

    Args:
        None

    Returns:
        True if calling function should 'succeed' (not be retried)
        False if calling function should 'fail' (be retried)
    """
    # Check if this has happened recently already
    fail_count = memcache.get(key=FAIL_COUNTER)

    # Retry up to three times
    fail_count = 0 if not fail_count else fail_count

    if fail_count < 3:
        logging.warning("Couldn't parse next page of results (attempt %s). "
                        "Failing task to force retry." % str(fail_count))
        fail_count += 1
        memcache.set(key=FAIL_COUNTER, value=fail_count, time=600)
        return False
    else:
        # This is a hacky check for whether we finished the alphabet. The last
        # name in DOCCS as of 11/13/2017 is 'ZYTEL', who's sentenced to life
        # and has no other crimes / disambig.
        current_session = get_open_sessions(most_recent_only=True)
        if current_session:
            last_scraped = current_session.last_scraped
        else:
            logging.error("No open sessions found! Bad state, ending scrape.")
            return True

        if not last_scraped:
            logging.error("Session isn't old enough to have a last_scraped name "
                          "yet, but no search results are coming back. Finding last "
                          "scraped name from earlier session.")

            # Get most recent sessions, including closed ones, and find
            # the last one to have a last_scraped name in it. These will
            # come back most-recent-first.
            recent_sessions = get_open_sessions(open_only=False)

            for session in recent_sessions:
                if session.last_scraped:
                    last_scraped = session.last_scraped
                    break

        if last_scraped[0:3] < "ZYT":

            # We haven't finished the alphabet yet. Most likely, we're failing
            # repeatedly because the server has lost state (e.g., went through
            # a maintenance period).
            logging.warning("Server has lost state. Kicking off new scrape "
                            "task for last name seen in results, and removing "
                            "other tasks with old state.")

            # Construct a resume_scraping request with a built-in delay, so
            # that the task it kicks off doesn't get eaten by our purging
            # the taskqueue with cleanup() immediately after this. Use 
            # urlfetch to get the GAE-added header to auth that this 
            # request came from our app.
            modified_resume_url = RESUME_URL
            resume_call = urlfetch.fetch(
                modified_resume_url,
                follow_redirects=False)

            # If call succeeded, purge the taskqueue and shut down this session
            # The order here is important, because I think cleanup() / purging 
            # the taskqueue will actually kill this task as well, so nothing 
            # after this will execute.
            if resume_call.status_code == 200:
                cleanup(end_session=True)
            else:
                # Fail the task to retry
                return False

            # Scraper should restart, wind-down this task gracefully.
            return True

        else:
            # We've run out of names, and the 'Next 4 results' button dumped us
            # back at the original search page. Log it, and end the query.
            logging.info("Looped. Ending scraping session.")
            cleanup()

            return True


def get_proxies(test_proxy=False):
    """
    get_proxies()
    Retrieves proxy information from datastore to use in requests to 
    third-party services.

    Args:
        test_proxy: Boolean, whether or not to use test proxy credentials

    Returns:
        Proxies dict for requests
    """
    # Pull the proxy user/pass from datastore
    user_var = "proxy_user"
    pass_var = "proxy_password"

    if test_proxy:
        user_var = "test_proxy_user"
        pass_var = "test_proxy_password"

    memcache_user_var = REGION + "_" + user_var
    memcache_pass_var = REGION + "_" + pass_var

    # Try to pull from memcache
    proxy_user = memcache.get(memcache_user_var)
    proxy_password = memcache.get(memcache_pass_var)

    if (proxy_user is None) or (proxy_password is None):

        # Fetch from datastore to repopulate
        user_result = EnvironmentVariable.query(ndb.AND(
            EnvironmentVariable.region == "all",
            EnvironmentVariable.name == user_var)).get()
        password_result = EnvironmentVariable.query(ndb.AND(
            EnvironmentVariable.region == "all",
            EnvironmentVariable.name == pass_var)).get()

        # If not found, raise an exception - no point in proceeding.
        if (not user_result) or (not password_result):
            logging.error("Couldn't retrieve proxy user/pass.")
            raise Exception("No proxy user/pass")
        else:
            # Set variables to their actual values
            proxy_user = str(user_result.value)
            proxy_password = str(password_result.value)

            # Re-store in memcache for an hour
            memcache.set(key=memcache_user_var, value=proxy_user, time=3600)
            memcache.set(key=memcache_pass_var, value=proxy_password, time=3600)

    # Return proxy dictionary
    proxy_credentials = proxy_user + ":" + proxy_password
    proxy_url = 'http://' + proxy_credentials + "@" + PROXY_DOMAIN

    proxies = {'http': proxy_url}

    return proxies
