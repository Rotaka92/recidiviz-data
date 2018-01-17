# Copyright 2017 Andrew Corp <andrew@andrewland.co> 
# All rights reserved.

from auth import authenticate_request
from datetime import datetime
from google.appengine.api import taskqueue
import logging
import webapp2


region_list = ["us_ny"]
available_actions = ["start", "stop", "resume"]
scrape_types = ["background, snapshot"]
FILENAME_PREFIX = "./name_lists/"
SNAPSHOT_DISTANCE_YEARS = 15
name_lists = {"us_ny": "us_ny_names.csv"}


class ScraperCommand(webapp2.RequestHandler):

    @authenticate_request
    def get(self):
        """
        get()
        Request handler to stops the requested scraper/s. Only accessible to 
        cron jobs.

        Args:
            region: String representation of a region code, e.g. us_ny

        Returns:
            HTTP 200 if successful 
            HTTP 400 if not
        """
        request_region = self.request.get('region', None).lower()
        request_action = self.request.get('action', None).lower()
        request_params = self.request.get.items()

        # Validate region and action requested
        if request_action not in available_actions:
            invalid_input("No recognized action parameter provided. Use "
                          "one of %s. Exiting." % str(available_actions))
            return

        if (request_region not in region_list) and (request_region != "all"):
            invalid_input("No valid region parameter provided. Use a "
                          "specific region code (e.g., us_ny) or 'all'. Exiting.")
            return

        # Parameters are valid, attempt requested action
        action_regions = []
        if request_region == "all":
            action_regions = region_list
        else:
            action_regions.append(request_region)

        for region in action_regions:
            issue_message = execute_command(region, request_action, request_params)
            if issue_message:
                # Parameters further down the decision tree were invalid
                invalid_input(issue_message)
                return

        return

    def invalid_input(log_message):
        # Invalid input, log the error and exit.
        logging.error(log_message)
        
        self.response.write('Missing or invalid parameters, see service logs.')
        self.response.set_status(400)


def execute_command(region, action, params):
    """
    execute_command()
    Calls the common method in the scraper for the relevant command, after
    validating any requisite params.

    Args: 
        region: string (e.g., us_ny)
        action: string (e.g., 'resume')
        params: iterable (e.g., '[('check', 'a'), ('check', 'b'), ('name', 'Bob')]')

    Returns:
        None if success
        Error messaging for logging if unsuccessful
    """
    # Import the appropriate scraper
    top_level = __import__("scraper")
    module = getattr(top_level, region)
    scraper = getattr(module, region + "_scraper")

    if action == "stop":
        scraper.stop_scrape()
    else:
        # Determine the scrape type - default to background if not provided
        scrape_type = get_param("scrape_type", params, "background")
        if scrape_type not in scrape_types:
            return ("'%s' is not a valid scrape type - use one of %s. "
                    "Exiting." % (scrape_type, str(scrape_types)))

        scraper.setup()

        if action == "resume":
            scraper.resume_scrape(scrape_type)
        elif action == "start":
            # Create target list for scraping
            target_list = get_target_list(scrape_type, region, params)

            # Clear prior queue for this scrape type
            queue = taskqueue.Queue(region + "-pull-" + scrape_type)
            queue.purge()

            # Build new queue from list
            tasks = []
            for item in target_list:
                payload = (item[0] + "," + item[1]) if len(item) > 1 else item[0]
                tasks.append(taskqueue.Task(payload=payload, method='PULL'))
            queue.add(tasks)

            # Start scraper
            scraper.start_query(scrape_type)


def get_param(param_name, params, default=None):
    """
    get_param()
    Takes an iterable list of key/value pairs (URL parameters from the request
    object), finds the key being sought, and returns its value or None if not
    found.

    Args:
        param_name: Name of the URL parameter being sought
        params: List of URL parameter key/value parts (e.g., 
            [("key", "val"), ("key2", "val2"), ...])

    Returns:
        Value for given param_name if found
        Provided default value if not found
        None if no default provided and not found
    """
    for key, val in params:
        if key == param_name:
            return val
    
    return default


def get_target_list(scrape_type, region, params):
    """
    get_target_list()
    Generates a list of query targets for a scraper. May be a list of common 
    names for a background search for a region, or of state ID numbers for
    a snapshot search.

    Args:
        scrape_type: Type of search. Can be 'background' or 'snapshot'
        params: List of URL parameter key/value parts (e.g., 
            [("key", "val"), ("key2", "val2"), ...])

    Returns:
        List of queries for the scraper to run
    """
    if scrape_type == "background":
        # Open name file for the region
        region_csv = open(FILENAME_PREFIX + name_lists[region], "rb")
        name_list = list(csv.reader(region_csv))

        # Check for name parameters
        given_names = get_param("given_names", params, "")
        surname = get_param("surname", params, "")

        if surname:
            get_name_list_subset(name_list, surname, given_names)

    else:
        # Snapshot scrape; pull list of current or recent inmates
        inmate_ids = []
        start_date = get_snapshot_start()
        
        # Get all snapshots showing inmates in prison within the date range
        # (Snapshot search aims to catch when they get out / facility changes)
        current_inmate_query = InmateSnapshot.query(ndb.AND(
            InmateSnapshot.snapshot_date > start_date,
            InmateSnapshot.is_released == False))
        current_inmate_snapshots = current_inmate_query.fetch()

        for snapshot in current_inmate_snapshots:
            record = snapshot.parent()
            inmate = record.parent()
            inmate_ids.append(inmate.inmate_id)

        # Pull a list of inmates with a release_date within the window (for
        # systems which provide this, lets us check on inmates released before
        # our background scraper first became aware of them but within window.)
        recently_released = Record.query(Record.last_release_date > start_date)
        recently_released_records = recently_released.fetch()

        for record in recently_released_records:
            inmate = record.parent()
            inmate_ids.append(inmate.inmate_id)

        # De-dup the two lists, return single list of inmate IDs
        return list(set(inmate_ids))


def get_name_list_subset(name_list, surname, given_names):
    """
    get_name_list_subset()
    Takes a parse CSV file and a name, attempts to find the name
    in the file, then (if found) returns the list only after that name.
    If not found, assumes the end-user is requesting to start a search 
    for this name specifically and returns list of only this name.

    Args:
        name_list: Parsed CSV in the form of
            [['Baker', 'Mandy'],
             ['del Toro', 'Guillero'],
             ['Ma', 'Yo Yo']]
        surname: User-provided string of a surname to find
        given_names: User-provided string of given names (may be blank)

    Returns:
        Subset of the original list
        None if name not found in list
    """
    try:

        if given_names:
            match_index = name_list.index([surname, given_names])
        else:
            match_index = name_list.index([surname])

        return name_list[match_index:]

    except ValueError:
        # Name not found in list
        return [[surname, given_names]]


def get_snapshot_start():
    """
    get_snapshot_date()
    Produces a datetime N years in the past, where N is the value of 
    SNAPSHOT_DISTANCE_YEARS.

    Args:
        None

    Returns:
        Datetime of date N years past
    """
    today = datetime.now()

    try:
        start_date = today.replace(year=today.year-SNAPSHOT_DISTANCE_YEARS)
    except ValueError:
        # That was a leap year, and today's 2/29
        start_date = today.replace(month=2, 
                                   day=28, 
                                   year=today.year-SNAPSHOT_DISTANCE_YEARS)

    return start_date


app = webapp2.WSGIApplication([
    ('/scraper_command', ScraperCommand)
], debug=False)
