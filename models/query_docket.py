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


from google.appengine.ext import ndb
from google.appengine.ext.ndb import polymodel


"""
DocketItem

Datastore model for a specific query that a scraper should run. This might be
one name in a set of names to search for, one inmate ID in a list of inmates
to snapshot, etc.

Fields:
    - created: (datetime) Creation date of the docket item
    - region: (string) Region code of the scraper this item is intended for 
    - scrape_type: (string) Type of query this item should be part of
    - content: (string) Payload of the item. Often the inmate ID, name, etc. 
"""
class DocketItem(ndb.Model):
    created = ndb.DateTimeProperty(auto_now_add=True)
    started = ndb.DateTimeProperty()
    region = ndb.StringProperty()
    scrape_type = ndb.StringProperty()
    content = ndb.StringProperty()
