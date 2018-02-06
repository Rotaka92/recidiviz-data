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
from models.inmate import Inmate


"""
UsNyInmate

Datastore model for a snapshot of a specific person in the prison system. This extends 
the general Inmate, which has the following fields:

See Inmate for pre-populated fields. UsNyInmate extends 
these by adding the following:
    - us_ny_inmate_id: (string) Same as inmate_id, but used as key for this entity type
        to force uniqueness / prevent collisions within the us_ny records

Note the duplicated record ID - this allows us to use this field as a key,
forcing uniqueness within the UsNy record space without forcing it across
all regions (as there may be record ID collisions between states).

"""
class UsNyInmate(Inmate):
    us_ny_inmate_id = ndb.StringProperty()