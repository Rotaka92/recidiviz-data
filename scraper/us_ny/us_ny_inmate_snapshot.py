# Copyright 2017 Andrew Corp <andrew@andrewland.co> 
# All rights reserved.


from google.appengine.ext import ndb
from models.inmate_snapshot import InmateSnapshot


"""
InmateSnapshot

Datastore model for the facility and other mutable details about an inmate 
at the time of a particular scraping. An inmate should have at least one 
entry for this from time of creation, but it will only be updated when 
the value changes. In very rare cases, the scraper might not find a value, 
in which case the 'facility' will be empty (but the snapshot still collected.)

Individual region scrapers are expected to create their own subclasses which
inherit these common properties, then add more if their region has more 
available. See us_ny_scraper.py for an example.

Fields:
    - snapshot_date: Python datetime for time of snapshot
    - facility: State-provided facility name
    - (see us_ny_record.py for remaining field descriptions)
"""
class UsNyInmateSnapshot(InmateSnapshot):
	last_custody_date = ndb.DateProperty()
    admission_type = ndb.StringProperty()
    county_of_commit = ndb.StringProperty()
    custody_status = ndb.StringProperty()
    earliest_release_date = ndb.DateProperty()
    earliest_release_type = ndb.StringProperty()
    parole_hearing_date = ndb.DateProperty()
    parole_hearing_type = ndb.StringProperty()
    parole_elig_date = ndb.DateProperty()
    cond_release_date = ndb.DateProperty()
    max_expir_date = ndb.DateProperty()
    max_expir_date_parole = ndb.DateProperty()
    max_expir_date_superv = ndb.DateProperty()
    parole_discharge_date = ndb.DateProperty()