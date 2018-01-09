# Copyright 2017 Andrew Corp <andrew@andrewland.co> 
# All rights reserved.


from google.appengine.ext import ndb


"""
ScrapeSession

Datastore model for a scraping session. Used by the scraper to discern
ScrapedRecord entities which predate the current session vs. those from
it (which are records that should be skipped).

Fields:
    - start: Date/time this session started
    - end: Date/time when this session finished
"""
class ScrapeSession(ndb.Model):
    start = ndb.DateTimeProperty(auto_now_add=True)
    end = ndb.DateTimeProperty()
    last_scraped = ndb.StringProperty()


"""
ScrapedRecord

Datastore model for a scraped record entry. We use this to track which records
we've already scraped in the session, and save ourselves and DOCCS the extra
network requests of re-scraping.

Fields:
    - record_id: Dept. ID Number, the ID for a record we've scraped
    - created_on: Date/time when this entry was created
"""
class ScrapedRecord(ndb.Model):
    record_id = ndb.StringProperty()
    created_on = ndb.DateTimeProperty(auto_now_add=True)